from JumpScale import j
import time
from JumpScale.portal.portal.auth import auth
from JumpScale.portal.portal import exceptions
from cloudbrokerlib.baseactor import BaseActor, wrap_remote
from JumpScale.portal.portal.async import async
from JumpScale.portal.portal import Validators


def _send_signup_mail(hrd, **kwargs):
    notifysupport = hrd.get("instance.openvcloud.cloudbroker.notifysupport")
    toaddrs = [kwargs['email']]

    fromaddr = hrd.get('instance.openvcloud.supportemail')
    if notifysupport == '1':
        toaddrs.append(fromaddr)

    message = j.core.portal.active.templates.render('cbportal/email/account/created.html', **kwargs)
    subject = j.core.portal.active.templates.render('cbportal/email/account/created.subject.txt', **kwargs)

    j.clients.email.send(toaddrs, fromaddr, subject, message, files=None)


class cloudbroker_account(BaseActor):

    def __init__(self):
        super(cloudbroker_account, self).__init__()
        self.syscl = j.clients.osis.getNamespace('system')

    def _checkAccount(self, accountId):
        account = self.models.account.search({'id': accountId, 'status': {'$ne': 'DESTROYED'}})[1:]
        if not account:
            raise exceptions.NotFound('Account name not found')
        if len(account) > 1:
            raise exceptions.BadRequest('Found multiple accounts for the account ID "%s"' % accountId)

        return account[0]

    @auth(['level1', 'level2', 'level3'])
    @async('Disabling Account', 'Finished disabling account', 'Failed to disable account')
    @wrap_remote
    def disable(self, accountId, reason, **kwargs):
        """
        Disable an account
        param:acountname name of the account
        param:reason reason of disabling
        result
        """
        account = self._checkAccount(accountId)
        account['deactivationTime'] = time.time()
        account['status'] = 'DISABLED'
        self.models.account.set(account)
        # stop all account's machines
        cloudspaces = self.models.cloudspace.search({'accountId': account['id']})[1:]
        for cs in cloudspaces:
            vmachines = self.models.vmachine.search({'cloudspaceId': cs['id'],
                                                     'status': {'$in': ['RUNNING', 'PAUSED']}
                                                     })[1:]
            for vmachine in vmachines:
                self.cb.actors.cloudapi.machines.stop(machineId=vmachine['id'])
        return True

    @auth(['level1', 'level2', 'level3'])
    @wrap_remote
    def create(self, name, username, emailaddress, maxMemoryCapacity=-1,
               maxVDiskCapacity=-1, maxCPUCapacity=-1, maxNetworkPeerTransfer=-1, maxNumPublicIP=-1, sendAccessEmails=True, **kwargs):

        if sendAccessEmails == 1:
            sendAccessEmails = True
        elif sendAccessEmails == 0:
            sendAccessEmails = False
        accounts = self.models.account.search({'name': name, 'status': {'$ne': 'DESTROYED'}})[1:]
        if accounts:
            raise exceptions.Conflict('Account name is already in use.')

        created = False
        if j.core.portal.active.auth.userExists(username):
            if emailaddress and not self.syscl.user.search({'id': username,
                                                            'emails': emailaddress})[1:]:
                raise exceptions.Conflict('The specified username and email do not match.')

            user = j.core.portal.active.auth.getUserInfo(username)
            emailaddress = user.emails[0] if user.emails else None
        else:
            if not emailaddress:
                raise exceptions.BadRequest('Email address is required for new users.')
            Validators.EMAIL(emailaddress)

            password = j.base.idgenerator.generateGUID()
            j.apps.cloudbroker.user.create(username=username, emailaddress=[emailaddress], password=password, groups=['user'])
            created = True

        now = int(time.time())
        locationurl = self.cb.actors.cloudapi.locations.getUrl().strip('/')

        account = self.models.account.new()
        account.name = name
        account.creationTime = now
        account.updateTime = now
        account.company = ''
        account.companyurl = ''
        account.status = 'CONFIRMED'
        account.sendAccessEmails = sendAccessEmails

        resourcelimits = {'CU_M': maxMemoryCapacity,
                          'CU_D': maxVDiskCapacity,
                          'CU_C': maxCPUCapacity,
                          'CU_NP': maxNetworkPeerTransfer,
                          'CU_I': maxNumPublicIP}
        self.cb.fillResourceLimits(resourcelimits)
        account.resourceLimits = resourcelimits

        ace = account.new_acl()
        ace.userGroupId = username
        ace.type = 'U'
        ace.right = 'CXDRAU'
        ace.status = 'CONFIRMED'
        accountid = self.models.account.set(account)[0]

        mail_args = {
            'account': name,
            'username': username,
            'email': emailaddress,
            'portalurl': locationurl
        }

        if created:
            # new user.
            validation_token = self.models.resetpasswordtoken.new()
            validation_token.id = j.base.idgenerator.generateGUID()
            validation_token.creationTime = int(time.time())
            validation_token.username = username

            self.models.resetpasswordtoken.set(validation_token)
            mail_args.update({
                'token': validation_token.id
            })

        if emailaddress:
            _send_signup_mail(hrd=self.hrd, **mail_args)

        return accountid

    @auth(['level1', 'level2', 'level3'])
    def enable(self, accountId, reason, **kwargs):
        """
        Enable an account
        param:acountID ID of the account
        param:reason reason of enabling
        result
        """
        account = self._checkAccount(accountId)
        if account['status'] != 'DISABLED':
            raise exceptions.BadRequest('Account is not disabled')

        account['status'] = 'CONFIRMED'
        self.models.account.set(account)
        return True

    @auth(['level1', 'level2', 'level3'])
    @wrap_remote
    def update(self, accountId, name, maxMemoryCapacity, maxVDiskCapacity, maxCPUCapacity,
               maxNetworkPeerTransfer, maxNumPublicIP, sendAccessEmails, **kwargs):
        """
        Update an account name or the maximum cloud units set on it
        Setting a cloud unit maximum to -1 will not put any restrictions on the resource

        :param accountId: id of the account to change
        :param name: name of the account
        :param maxMemoryCapacity: max size of memory in GB
        :param maxVDiskCapacity: max size of aggregated vdisks in GB
        :param maxCPUCapacity: max number of cpu cores
        :param maxNASCapacity: max size of primary(NAS) storage in TB
        :param maxNetworkOptTransfer: max sent/received network transfer in operator
        :param maxNetworkPeerTransfer: max sent/received network transfer peering
        :param maxNumPublicIP: max number of assigned public IPs
        :return: True if update was successful
        """

        if sendAccessEmails == 1:
            sendAccessEmails = True
        elif sendAccessEmails == 0:
            sendAccessEmails = False

        resourcelimits = {'CU_M': maxMemoryCapacity,
                          'CU_D': maxVDiskCapacity,
                          'CU_C': maxCPUCapacity,
                          'CU_NP': maxNetworkPeerTransfer,
                          'CU_I': maxNumPublicIP}
        self.cb.fillResourceLimits(resourcelimits)
        maxMemoryCapacity = resourcelimits['CU_M']
        maxVDiskCapacity = resourcelimits['CU_D']
        maxCPUCapacity = resourcelimits['CU_C']
        maxNetworkPeerTransfer = resourcelimits['CU_NP']
        maxNumPublicIP = resourcelimits['CU_I']

        return self.cb.actors.cloudapi.accounts.update(accountId=accountId, name=name, maxMemoryCapacity=maxMemoryCapacity,
                                                       maxVDiskCapacity=maxVDiskCapacity, maxCPUCapacity=maxCPUCapacity, maxNetworkPeerTransfer=maxNetworkPeerTransfer,
                                                       maxNumPublicIP=maxNumPublicIP, sendAccessEmails=sendAccessEmails)

    @auth(['level1', 'level2', 'level3'])
    def deleteAccounts(self, accountIds, reason, **kwargs):
        for accountId in accountIds:
            self.delete(accountId, reason, **kwargs)

    @auth(['level1', 'level2', 'level3'])
    def delete(self, accountId, reason, **kwargs):
        """
        Complete delete an account from the system
        """
        account = self._checkAccount(accountId)
        startstate = account['status']

        def restorestate(eco):
            account = self.models.account.get(accountId)
            account.status = startstate
            self.models.account.set(account)

        ctx = kwargs['ctx']
        ctx.events.runAsync(self._delete,
                            (accountId, reason, kwargs),
                            {},
                            'Deleting Account %(name)s' % account,
                            'Finished deleting Account',
                            'Failed to delete Account',
                            errorcb=restorestate)

    def _delete(self, accountId, reason, kwargs):
        ctx = kwargs['ctx']
        account = self.models.account.get(accountId)
        title = 'Deleting Account %s' % account.name
        account.status = 'DESTROYING'
        self.models.account.set(account)
        query = {'accountId': accountId, 'status': {'$ne': 'DESTROYED'}}

        # first delete all images and dependant vms
        images = self.models.image.search({'accountId': accountId})[1:]
        for image in images:
            ctx.events.sendMessage(title, 'Deleting Image %(name)s' % image)
            for vm in self.models.vmachine.search({'imageId': image['id'], 'status': {'$ne': 'DESTROYED'}})[1:]:
                ctx.events.sendMessage(title, 'Deleting dependant Virtual Machine %(name)s' % image)
                j.apps.cloudbroker.machine.destroy(vm['id'], reason)
            self.cb.actors.cloudapi.images.delete(imageId=image['id'])
        cloudspaces = self.models.cloudspace.search(query)[1:]
        for cloudspace in cloudspaces:
            j.apps.cloudbroker.cloudspace._destroy(cloudspace, reason, kwargs['ctx'])
        account = self.models.account.get(accountId)
        account.status = 'DESTROYED'
        self.models.account.set(account)
        return True

    @auth(['level1', 'level2', 'level3'])
    @wrap_remote
    def addUser(self, accountId, username, accesstype, **kwargs):
        """
        Give a user access rights.
        Access rights can be 'R' or 'W'
        param:accountId id of the account
        param:username id of the user to give access or emailaddress to invite an external user
        param:accesstype 'R' for read only access, 'W' for Write access
        result bool
        """
        self._checkAccount(accountId)
        user = self.cb.checkUser(username, activeonly=False)
        if user:
            self.cb.actors.cloudapi.accounts.addUser(accountId=accountId, userId=username, accesstype=accesstype)
        else:
            raise exceptions.NotFound('User with username %s is not found' % username)
        return True

    @auth(['level1', 'level2', 'level3'])
    @wrap_remote
    def deleteUser(self, accountId, username, recursivedelete, **kwargs):
        """
        Delete a user from the account
        """
        account = self._checkAccount(accountId)
        accountId = account['id']
        user = self.cb.checkUser(username)
        if user:
            userId = user['id']
        else:
            # external user, delete ACE that was added using emailaddress
            userId = username
        self.cb.actors.cloudapi.accounts.deleteUser(accountId=accountId, userId=userId, recursivedelete=recursivedelete)
        return True
