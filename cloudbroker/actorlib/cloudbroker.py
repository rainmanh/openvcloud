from js9 import j
from JumpScale9Portal.portal import exceptions
from cloudbroker.actorlib import enums, network
from .gridmanager.client import getGridClient
from mongoengine.queryset.visitor import Q
from .netmgr import NetManager
import netaddr
import uuid
import random
import string
import mongolock
import re
import json

models = j.portal.tools.models.cloudbroker
MACHINE_INVALID_STATES = ['ERROR', 'DESTROYED', 'DESTROYING']


def removeConfusingChars(input):
    return input.replace('0', '').replace('O', '').replace('l', '').replace('I', '')


class CloudBroker(object):
    _resourceProviderId2StackId = dict()

    def __init__(self):
        self._actors = None
        self.syscl = j.portal.tools.models.system
        self.cbcl = models
        self.machine = Machine(self)
        self.cloudspace = CloudSpace(self)
        self.netmgr = NetManager(self, models)

    @property
    def actors(self):
        return j.apps

    def markProvider(self, stack, eco):
        stack.error += 1
        if stack.error >= 2:
            stack.status = 'ERROR'
            stack.eco = eco.guid
        stack.save()

    def clearProvider(self, stack):
        stack.modify(eco=None, error=0, status='ENABLED')

    def getBestStack(self, location, image=None, excludelist=[]):
        client = getGridClient(location, models)
        capacityinfo = self.getCapacityInfo(location, client, image)
        if not capacityinfo:
            return -1
        capacityinfo = [node for node in capacityinfo if node['id'] not in excludelist]
        if not capacityinfo:
            return -1

        return capacityinfo[0]  # is sorted by least used

    def getCapacityInfo(self, location, client, image=None):
        resourcesdata = list()
        activenodes = [node['id'] for node in client.getActiveNodes()]
        if image:
            stacks = models.Stack.objects(images=image, location=location)
        else:
            stacks = models.Stack.objects(location=location)
        for stack in stacks:
            if stack.status == 'ENABLED':
                if stack.referenceId not in activenodes:
                    continue
                # search for all vms running on the stacks
                usedvms = models.VMachine.objects(stack=stack, status__nin=MACHINE_INVALID_STATES)
                if usedvms:
                    stack.usedmemory = sum(vm.memory for vm in usedvms)
                else:
                    stack.usedmemory = 0
                resourcesdata.append(stack)
        resourcesdata.sort(key=lambda s: s.usedmemory)
        return resourcesdata

    def registerNetworkIdRange(self, locationId, start, end, **kwargs):
        """
        Add a new network idrange
        param:start start of the range
        param:end end of the range
        result
        """
        newrange = set(range(int(start), int(end) + 1))
        networkids = models.NetworkIds.objects(location=locationId).first()
        if networkids:
            cloudspaces = models.Cloudspace.objects(status__in=['DEPLOYED', 'VIRTUAL'], location=locationId)
            usednetworkids = {space['networkId'] for space in cloudspaces}
            if usednetworkids.intersection(newrange):
                raise exceptions.Conflict("Conflicting start/end range given")
            networkids.update(add_to_set__freeeNetworkIds=newrange)
        else:
            models.NetworkIds(
                location=locationId,
                freeNetworkIds=list(newrange)
            ).save()
        return True

    def getFreeNetworkId(self, location, **kwargs):
        """
        Get a free NetworkId
        result
        """
        networkids = models.NetworkIds.objects(location=location).first()
        if not networkids:
            raise exceptions.ServiceUnavailable("No networkids configured for location")
        for netid in networkids.freeNetworkIds:
            res = networkids.update(full_result=True, pull__freeNetworkIds=netid)
            if res['nModified'] == 1:
                networkids.update(push__usedNetworkIds=netid)
                return netid

    def releaseNetworkId(self, location, networkid, **kwargs):
        """
        Release a networkid.
        param:networkid int representing the netowrkid to release
        result bool
        """
        networkids = models.NetworkIds.objects(location=location).first()
        if not networkids:
            raise exceptions.ServiceUnavailable("No networkids configured for location")
        networkids.update(pull__usedNetworkIds=networkid, push__freeNetworkIds=networkid)
        return True

    def checkUser(self, username, activeonly=True):
        """
        Check if a user exists with the given username or email address

        :param username: username or emailaddress of the user
        :param activeonly: only return activated users if set to True
        :return: User if found
        """
        users = self.syscl.User.objects((Q(name=username) | Q(emails=username)))
        if activeonly:
            users = users.filter(Q(active=True))
        user = users.first()
        if user:
            return user
        else:
            return None

    def updateResourceInvitations(self, username, emailaddress):
        """
        Update the invitations in ACLs of Accounts, Cloudspaces and Machines after user registration

        :param username: username the user has registered with
        :param emailaddress: emailaddress of the registered users
        :return: True if resources were updated
        """
        # Validate that only one email address was sent for updating the resources
        if len(emailaddress.split(',')) > 1:
            raise exceptions.BadRequest('Cannot update resource invitations for a list of multiple '
                                        'email addresses')

        for account in self.cbcl.account.search({'acl.userGroupId': emailaddress})[1:]:
            accountobj = self.cbcl.account.get(account['guid'])
            for ace in accountobj.acl:
                if ace.userGroupId == emailaddress:
                    # Update userGroupId and status after user registration
                    ace.userGroupId = username
                    ace.status = 'CONFIRMED'
                    self.cbcl.account.set(accountobj)
                    break

        for cloudspace in self.cbcl.cloudspace.search({'acl.userGroupId': emailaddress})[1:]:
            cloudspaceobj = self.cbcl.cloudspace.get(cloudspace['guid'])
            for ace in cloudspaceobj.acl:
                if ace.userGroupId == emailaddress:
                    # Update userGroupId and status after user registration
                    ace.userGroupId = username
                    ace.status = 'CONFIRMED'
                    self.cbcl.cloudspace.set(cloudspaceobj)
                    break

        for vmachine in self.cbcl.vmachine.search({'acl.userGroupId': emailaddress})[1:]:
            vmachineobj = self.cbcl.vmachine.get(vmachine['guid'])
            for ace in cloudspaceobj.acl:
                if ace.userGroupId == emailaddress:
                    # Update userGroupId and status after user registration
                    ace.userGroupId = username
                    ace.status = 'CONFIRMED'
                    self.cbcl.vmachine.set(vmachineobj)
                    break

        return True

    def isaccountuserdeletable(self, userace, acl):
        if set(userace.right) != set('ARCXDU'):
            return True
        else:
            otheradmins = filter(lambda a: set(a.right) == set('ARCXDU') and a != userace, acl)
            if not otheradmins:
                return False
            else:
                return True

    def isValidEmailAddress(self, emailaddress):
        r = re.compile('^[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}$')
        return r.match(emailaddress) is not None

    def isValidRole(self, accessrights):
        """
        Validate that the accessrights map to a valid access role on a resource
        'R' for read only access, 'RCX' for Write and 'ARCXDU' for Admin

        :param accessrights: string with the accessrights to verify
        :return: role name if a valid set of permissions, otherwise fail with an exception
        """
        if accessrights == 'R':
            return 'Read'
        elif set(accessrights) == set('RCX'):
            return 'Read/Write'
        elif set(accessrights) == set('ARCXDU'):
            return 'Admin'
        else:
            raise exceptions.BadRequest('Invalid set of access rights "%s". Please only use "R" '
                                        'for Read, "RCX" for Read/Write and "ARCXDU" for Admin '
                                        'access.' % accessrights)

    def fillResourceLimits(self, resource_limits, preserve_none=False):
        for limit_type in ['CU_M', 'CU_D', 'CU_C', 'CU_NP', 'CU_I']:
            if limit_type not in resource_limits or resource_limits[limit_type] is None:
                resource_limits[limit_type] = None if preserve_none else -1
            elif resource_limits[limit_type] < -1 or resource_limits[limit_type] == 0:
                raise exceptions.BadRequest('A resource limit should be a positive number or -1 (unlimited).')
            if limit_type == 'CU_M':
                resource_limits[limit_type] = resource_limits[limit_type] and float(resource_limits[limit_type])
            else:
                resource_limits[limit_type] = resource_limits[limit_type] and int(resource_limits[limit_type])
        maxVDiskCapacity = resource_limits['CU_D']
        if maxVDiskCapacity is not None and maxVDiskCapacity != -1 and maxVDiskCapacity < 10:
            raise exceptions.BadRequest("Minimum disk capacity for cloudspace is 10GB.")


class CloudSpace(object):

    def __init__(self, cb):
        self.cb = cb
        self.network = network.Network(models)

    def release_resources(self, cloudspace, releasenetwork=True):
        #  delete vfw
        if cloudspace.stack:
            self.cb.netmgr.destroy(cloudspace)
        if cloudspace.networkId and releasenetwork:
            self.cb.releaseNetworkId(cloudspace.location, cloudspace.networkId)
            cloudspace.networkId = None
        if cloudspace.externalnetworkip:
            self.network.releaseExternalIpAddress(cloudspace.externalnetwork, cloudspace.externalnetworkip)
            cloudspace.externalnetworkip = None
        return cloudspace

    def get(self, cloudspaceId):
        cloudspace = models.Cloudspace.get(cloudspaceId)
        if not cloudspace:
            raise exceptions.NotFound("Cloud space with id %s does not exists" % cloudspaceId)

        return cloudspace


class Machine(object):

    def __init__(self, cb):
        self.cb = cb
        self.rcl = j.core.db

    def cleanup(self, machine):
        # this method might be called by muiltiple layers so we dont care of delete fails
        for diskid in machine.disks:
            try:
                models.disk.delete(diskid)
            except:
                pass
        try:
            models.vmachine.delete(machine.id)
        except:
            pass

    def validateCreate(self, cloudspace, name, memory, vcpus, imageId, disksize, datadisks):
        self.assertName(cloudspace, name)
        if not disksize:
            raise exceptions.BadRequest("Invalid disksize %s" % disksize)

        for datadisksize in datadisks:
            if datadisksize > 2000000:
                raise exceptions.BadRequest("Invalid data disk size {}GB max size is 2000GB".format(datadisksize))

        if cloudspace.status == 'DESTROYED':
            raise exceptions.BadRequest('Can not create machine on destroyed Cloud Space')

        image = models.Image.get(imageId)
        if disksize < image.size:
            raise exceptions.BadRequest(
                "Disk size of {}GB is to small for image {}, which requires at least {}GB.".format(disksize, image.name, image.size))
        if image.status != "ENABLED":
            raise exceptions.BadRequest("Image {} is disabled.".format(imageId))

        if models.VMachine.objects(status__ne='DESTROYED', cloudspace=cloudspace.id).count() >= 250:
            raise exceptions.BadRequest("Can not create more than 250 Virtual Machines per Cloud Space")

        return image

    def assertName(self, cloudspace, name):
        if not name or not name.strip():
            raise ValueError("Machine name can not be empty")
        if models.VMachine.objects(cloudspace=cloudspace.id, status__nin=MACHINE_INVALID_STATES, name=name).count() > 0:
            raise exceptions.Conflict('Selected name already exists')

    def getFreeMacAddress(self, location, **kwargs):
        """
        Get a free macaddres in this environment
        result
        """
        mac = models.Macaddress.objects(location=location).modify(upsert=True, location=location, inc__count=1)
        if not mac:
            count = 0
        else:
            count = mac.count
        firstmac = netaddr.EUI('52:54:00:00:00:00')
        newmac = int(firstmac) + count
        macaddr = netaddr.EUI(newmac)
        macaddr.dialect = netaddr.mac_eui48
        return str(macaddr).replace('-', ':').lower()

    def createModel(self, name, description, cloudspace, image, memory, vcpus, disksize, datadisks):
        datadisks = datadisks or []
        hostName = self.make_hostname(name)

        machine = models.VMachine(
            name=name,
            cloudspace=cloudspace,
            description=description,
            status='HALTED',
            memory=memory,
            vcpus=vcpus,
            hostName=hostName,
            image=image,
            type='VIRTUAL'
        )

        def addDisk(order, size, type, name=None):
            disk = models.Disk(
                name=name or 'Disk nr %s' % order,
                description='Machine disk fo type %s' % type,
                size=size,
                iops=2000,
                account=cloudspace.account,
                location=cloudspace.location,
                type=type
            )
            disk.save()
            machine.disks.append(disk)
            return disk

        addDisk(-1, disksize, 'BOOT', 'Boot disk')
        diskinfo = []
        for order, datadisksize in enumerate(datadisks):
            diskid = addDisk(order, int(datadisksize), 'D')
            diskinfo.append((diskid, int(datadisksize)))

        account = models.VMAccount()
        if hasattr(image, 'username') and image.username:
            account.login = image.username
        elif image.type != 'Custom Templates':
            account.login = 'gig'
        else:
            account.login = 'Custom login'
            account.password = 'Custom password'

        if hasattr(image, 'password') and image.password:
            account.password = image.password

        if not account.password:
            length = 6
            chars = removeConfusingChars(string.ascii_letters + string.digits)
            letters = [removeConfusingChars(string.ascii_lowercase), removeConfusingChars(string.ascii_uppercase)]
            passwd = ''.join(random.choice(chars) for _ in range(length))
            passwd = passwd + random.choice(string.digits) + random.choice(letters[0]) + random.choice(letters[1])
            account.password = passwd

        machine.accounts.append(account)

        nic = models.Nic(
            macAddress=self.getFreeMacAddress(cloudspace.location),
            deviceName='vm-{}-{:04x}'.format(machine.id, cloudspace.networkId),
            networkId=cloudspace.networkId,
            type='vxlan'
        )
        lock = mongolock.MongoLock(client=models.Cloudspace._get_collection().database.client)
        with lock(str(cloudspace.id), 'getFreeIPAddress', expire=60, timeout=10):
            nic.ipAddress = self.cb.netmgr.getFreeIPAddress(cloudspace)
            machine.nics.append(nic)
            machine.save()

        return machine

    def _getBestClient(self, machine, location, newstackId, excludelist, image=None):
        client = None
        if not newstackId:
            stack = self.cb.getBestStack(location, image, excludelist)
            if stack == -1:
                raise exceptions.ServiceUnavailable(
                    'Not enough resources available to provision the requested machine')
            client = getGridClient(location, models)
        else:
            stack = models.Stack.get(newstackId)
            client = getGridClient(stack.location, models)
            activenodes = [node['id']for node in client.getActiveNodes()]
            if stack['referenceId'] not in activenodes:
                raise exceptions.ServiceUnavailable(
                    'Not enough resources available to provision the requested machine')
        return stack, client

    def make_hostname(self, name):
        name = name.strip().lower()
        return re.sub('[^a-z0-9-]', '', name)[:63] or 'vm'

    def create(self, machine, cloudspace, image, stackId):
        excludelist = []
        newstackId = stackId
        while True:
            disks = []
            stack, client = self._getBestClient(machine, cloudspace.location, newstackId, excludelist, image)
            machine.stack = stack

            if image not in stack.images:
                self.cleanup(machine)
                raise exceptions.BadRequest("Image is not available on requested stack")

            try:
                for disk in machine.disks:
                    disks.append(disk)
                    if disk.type == 'BOOT':
                        client.storage.createVolume(disk, image)
                    else:
                        client.storage.createVolume(disk)
            except Exception as e:
                eco = j.errorhandler.processPythonExceptionObject(e)
                self.cleanup(machine)
                raise exceptions.ServiceUnavailable('Not enough storage resources available to provision the requested machine')
            try:
                machine.save()
                client.machine.create(machine, disks, stack.referenceId)
                break
            except Exception as e:
                eco = j.errorhandler.processPythonExceptionObject(e)
                self.cb.markProvider(stack, eco)
                newstackId = 0
                machine.modify(status='ERROR')
                if stackId:
                    self.cleanup(machine)
                    raise exceptions.ServiceUnavailable('Not enough cpu resources available to provision the requested machine')
                else:
                    excludelist.append(stack['id'])
                    newstackId = 0
        self.cb.clearProvider(stack)
        machine.modify(stack=stack, status='RUNNING')
        return machine.id

    def get_cloudinit_data(self, machine):
        image = machine.image
        hostname = machine.hostName
        userdata = {}
        if image.type.lower().strip() != 'windows':
            userdata = {'users': [],
                        # 'password': password  # might break cloud init reminder for further testing.
                        'ssh_pwauth': True,
                        'manage_etc_hosts': True,
                        'chpasswd': {'expire': False}}
            for account in machine.accounts:
                userdata['users'].append({'name': account.login,
                                          'plain_text_passwd': account.password,
                                          'lock-passwd': False,
                                          'shell': '/bin/bash',
                                          'sudo': 'ALL=(ALL) ALL'})
            metadata = {'local-hostname': hostname}
        else:
            admin = machine.accounts[0]
            metadata = {'admin_pass': admin.password, 'hostname': hostname}
        return {'userdata': json.dumps(userdata), 'metadata': json.dumps(metadata)}

    def start(self, machine, stack=None):
        excludelist = []
        newstack = stack

        while True:
            stack, client = self._getBestClient(machine, machine.cloudspace.location, newstack, excludelist, machine.image)
            try:
                client.machine.start(machine.id, stack['referenceId'])
                break
            except Exception as e:
                eco = j.errorhandler.processPythonExceptionObject(e)
                self.cb.markProvider(stack, eco)
                newstack = None
                machine.modify(status='ERROR')
                if stack:
                    raise exceptions.ServiceUnavailable('Not enough cpu resources available to provision the requested machine')
                else:
                    excludelist.append(stack['id'])
                    newstack = None
                self.cb.clearProvider(stack)
        machine.modify(stack=stack)
        return machine.id

    def stop(self, machine, force=False):
        stack = machine.stack
        client = getGridClient(stack.location, models)
        try:
            if force:
                client.machine.shutdown(machine.id, stack.referenceId)
            else:
                client.machine.stop(machine.id, stack.referenceId)
        except Exception as e:
            eco = j.errorhandler.processPythonExceptionObject(e)
            self.cb.markProvider(stack, eco)
            machine.modify(status='ERROR')
            raise
        return machine.id

    def get(self, machine):
        client = getGridClient(machine.stack.location, models)
        return client.machine.get(machine.id, machine.stack.referenceId)

    def getConsoleUrl(self, machine):
        token = str(uuid.uuid4())
        vncs = models.VNC.objects
        if not vncs:
            raise exceptions.BadRequest("Not console output available")
        self.rcl.set('vnc:{}'.format(token), str(machine.id), ex=60)
        vnc = random.choice(vncs)
        return "{url}{token}".format(url=vnc['url'], token=token)

    def getConsoleInfo(self, token):
        machineId = self.rcl.get('vnc:{}'.format(token)).decode()
        if not machineId:
            raise exceptions.NotFound("Could not find token")
        machine = models.VMachine.get(machineId)
        machineinfo = self.get(machine)
        client = getGridClient(machine.stack.location, models)
        nodeinfo = client.getNode(machine.stack.referenceId)
        return {'host': nodeinfo['ipaddress'], 'port': machineinfo['vnc']}

    def pause(self, machine):
        client = getGridClient(machine.stack.location, models)
        try:
            client.machine.pause(machine.id, machine.stack.referenceId)
        except Exception as e:
            eco = j.errorhandler.processPythonExceptionObject(e)
            self.cb.markProvider(machine.stack, eco)
            machine.modify(status='ERROR')
            raise
        return machine.id

    def update(self, machine):
        client = getGridClient(machine.stack.location, models)
        return client.machine.update(machine, machine.stack.referenceId)

    def resume(self, machine):
        client = getGridClient(machine.stack.location, models)
        try:
            client.machine.resume(machine.id, machine.stack.referenceId)
        except Exception as e:
            eco = j.errorhandler.processPythonExceptionObject(e)
            self.cb.markProvider(machine.stack, eco)
            machine.modify(status='ERROR')
            raise
        return machine.id

    def destroy(self, machine):
        if machine.stack:
            client = getGridClient(machine.stack.location, models)
            client.machine.destroy(machine.id, machine.stack.referenceId)
        for disk in machine.disks:
            client.storage.deleteVolume(disk)

# not api not implemented use start and stop instead
    # def reboot(self, machine):
    #     stackId = machine.stackId
    #     stack = models.stack.get(stackId)
    #     client = getGridClient(stack.gid, models)
    #     try:
    #         client.machine.reboot(machine.id, stack.refrenceId)
    #     except Exception as e:
    #         eco = j.errorhandler.processPythonExceptionObject(e)
    #         self.cb.markProvider(stack.id, eco)
    #         machine.status = 'ERROR'
    #         models.vmachine.updateSearch({'id': machine.id}, {'$set': {'status': 'ERROR'}})
    #         raise
    #     tags = str(machine.id)
    #     return machine.id

    def status(self, machine):
        client = getGridClient(machine.stack.location, models)
        status = client.machine.status(machine.id, machine.stack.referenceId)
        return getattr(enums.MachineStatus, status.lower())

    def rollback(self, machine, epoch):
        stackId = machine.stackId
        stack = models.stack.get(stackId)
        client = getGridClient(stack.gid, models)
        for diskId in machine.disks:
            disk = models.disk.get(diskId)
            client.storage.rollbackVolume(disk, epoch)