from JumpScale import j
import time
import JumpScale.grid.osis
from JumpScale.portal.portal.auth import auth

class cloudbroker_account(j.code.classGetBase()):
    def __init__(self):
        self._te={}
        self.actorname="account"
        self.appname="cloudbroker"
        self._cb = None
        self.cbcl = j.core.osis.getClientForNamespace('cloudbroker')
        self.syscl = j.core.osis.getClientForNamespace('system')
        self.accounts_actor = self.cb.extensions.imp.actors.cloudapi.accounts
        self.machines_actor = self.cb.extensions.imp.actors.cloudapi.machines
        self.users_actor = self.cb.extensions.imp.actors.cloudapi.users

    @property
    def cb(self):
        if not self._cb:
            self._cb = j.apps.cloudbroker.iaas
        return self._cb

    def _checkAccount(self, accountname, ctx):
        account = self.cbcl.account.simpleSearch({'name':accountname})
        if not account:
            headers = [('Content-Type', 'application/json'), ]
            ctx.start_response("404", headers)
            return False, 'Account name not found'
        if len(account) > 1:
            headers = [('Content-Type', 'application/json'), ]
            ctx.start_response('400', headers)
            return 'Found multiple accounts for the account name "%s"' % accountname

        return True, account[0]

    def _checkUser(self, username):
        user = self.syscl.user.simpleSearch({'id':username})
        if not user:
            return False, 'Username "%s" not found' % username
        return True, user[0]

    @auth(['level1','level2'])
    def disable(self, accountname, reason, **kwargs):
        """
        Disable an account
        param:acountname name of the account
        param:reason reason of disabling
        result
        """
        ctx = kwargs["ctx"]
        check, result = self._checkAccount(accountname, ctx)
        if not check:
            return result
        else:
            msg = 'Account: %s\nReason: %s' % (accountname, reason)
            subject = 'Disabling account: %s' % accountname
            ticketId = j.tools.whmcs.tickets.create_ticket(subject, msg, 'High')
            account = result
            account['deactivationTime'] = time.time()
            account['status'] = 'DISABLED'
            self.cbcl.account.set(account)
            # stop all account's machines
            cloudspaces = self.cbcl.cloudspace.search({'accountId': account['id']})[1:]
            for cs in cloudspaces:
                vmachines = self.cbcl.vmachine.search({'cloudspaceId': cs['id'], 'status': 'RUNNING'})[1:]
                for vmachine in vmachines:
                    self.machines_actor.stop(vmachine['id'])
            j.tools.whmcs.tickets.close_ticket(ticketId)
            return True

    @auth(['level1','level2'])
    def create(self, username, name, emailaddress, password, location, **kwargs):
        ctx = kwargs["ctx"]
        check, result = self._checkUser(username)
        if check:
            headers = [('Content-Type', 'application/json'), ]
            ctx.start_response("409", headers)
            return "Username %s already exists" % username
        return self.users_actor.register(username, name, emailaddress, password, None, None, location, None)

    @auth(['level1','level2'])
    def enable(self, accountname, reason, **kwargs):
        """
        Enable an account
        param:acountname name of the account
        param:reason reason of enabling
        result
        """
        ctx = kwargs["ctx"]
        check, result = self._checkAccount(accountname, ctx)
        if not check:
            return result
        else:
            account = result
            if account['status'] != 'DISABLED':
                ctx = kwargs["ctx"]
                headers = [('Content-Type', 'application/json'), ]
                ctx.start_response("400", headers)
                return 'Account is not disabled'

            account['status'] = 'CONFIRMED'
            self.cbcl.account.set(account)
            return True

    @auth(['level1','level2'])
    def rename(self, accountname, name, **kwargs):
        """
        Rename an account
        param:accountname name of the account
        param:name new name of the account
        result
        """
        ctx = kwargs["ctx"]
        check, result = self._checkAccount(accountname, ctx)
        if not check:
            return result
        else:
            account = result
            account['name'] = name
            self.cbcl.account.set(account)
            return True

    @auth(['level1','level2'])
    def delete(self, accountname, reason, **kwargs):
        """
        Complete delete an acount from the system
        """
        ctx = kwargs["ctx"]
        check, result = self._checkAccount(accountname, ctx)
        if not check:
            return result
        else:
            accountId = result['id']
            query = {'accountId': accountId, 'status': {'$ne': 'DESTROYED'}}
            cloudspaces = self.cbcl.cloudspace.search(query)[1:]
            for cloudspace in cloudspaces:
                cloudspacename = cloudspace['name']
                cloudspaceid = cloudspace['id']
                j.apps.cloudbroker.cloudspace.destroy(accountname, cloudspacename, cloudspaceid, reason, **kwargs)
            account = self.cbcl.account.get(accountId)
            account.status = 'DESTROYED'
            self.cbcl.account.set(account)
            return True

    @auth(['level1','level2'])
    def addUser(self, accountname, username, accesstype, **kwargs):
        """
        Give a user access rights.
        Access rights can be 'R' or 'W'
        param:accountname id of the account
        param:username id of the user to give access
        param:accesstype 'R' for read only access, 'W' for Write access
        result bool
        """
        ctx = kwargs["ctx"]
        check, result = self._checkAccount(accountname, ctx)
        if not check:
            return result
        accountId = result['id']
        check, result = self._checkUser(username)
        if not check:
            headers = [('Content-Type', 'application/json'), ]
            ctx.start_response("404", headers)
            return result
        userId = result['id']
        self.accounts_actor.addUser(accountId, userId, accesstype)
        return True

    @auth(['level1','level2'])
    def deleteUser(self, accountname, username, **kwargs):
        """
        Delete a user from the account
        """
        ctx = kwargs["ctx"]
        check, result = self._checkAccount(accountname, ctx)
        if not check:
            return result
        accountId = result['id']
        check, result = self._checkUser(username)
        if not check:
            headers = [('Content-Type', 'application/json'), ]
            ctx.start_response("404", headers)
            return result
        userId = result['id']
        self.accounts_actor.deleteUser(accountId, userId)
        return True
