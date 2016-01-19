from JumpScale import j
from JumpScale.portal.portal.auth import auth as audit
from JumpScale.portal.portal import exceptions
from cloudbrokerlib import authenticator, enums
from cloudbrokerlib.baseactor import BaseActor
from cloudbrokerlib import authenticator, network
import time
import itertools


class RequireState(object):
    def __init__(self, state, msg):
        self.state = state
        self.msg = msg

    def __call__(self, func):
        def wrapper(s, **kwargs):
            machineId = int(kwargs['machineId'])
            if not s.models.vmachine.exists(machineId):
                raise exceptions.NotFound("Machine with id %s was not found" % machineId)

            machine = s.get(machineId)
            if not machine['status'] == self.state:
                raise exceptions.Conflict(self.msg)
            return func(s, **kwargs)

        return wrapper


class cloudapi_machines(BaseActor):
    """
    API Actor api, this actor is the final api a enduser uses to manage his resources

    """
    def __init__(self):
        super(cloudapi_machines, self).__init__()
        self.osisclient = j.core.portal.active.osis
        self.acl = j.clients.agentcontroller.get()
        self.osis_logs = j.clients.osis.getCategory(self.osisclient, "system", "log")
        self._minimum_days_of_credit_required = float(self.hrd.get("instance.openvcloud.cloudbroker.creditcheck.daysofcreditrequired"))
        self.netmgr = j.apps.jumpscale.netmgr
        self.network = network.Network(self.models)
        self.systemodel = j.clients.osis.getNamespace('system')

    def _action(self, machineId, actiontype, newstatus=None, **kwargs):
        """
        Perform a action on a machine, supported types are STOP, START, PAUSE, RESUME, REBOOT
        param:machineId id of the machine
        param:actiontype type of the action(e.g stop, start, ...)
        result bool

        """
        machine = self._getMachine(machineId)
        provider, node = self._getProviderAndNode(machineId)
        if node.extra.get('locked', False):
            raise exceptions.Conflict("Can not %s a locked Machine" % actiontype)
        actionname = "%s_node" % actiontype.lower()
        method = getattr(provider.client, actionname, None)
        if not method:
            method = getattr(provider.client, "ex_%s" % actionname.lower(), None)
            if not method:
                raise RuntimeError("Action %s is not support on machine %s" % (actiontype, machineId))
        if newstatus and newstatus != machine.status:
            machine.status = newstatus
            self.models.vmachine.set(machine)
        tags = str(machineId)
        j.logger.log(actiontype.capitalize(), category='machine.history.ui', tags=tags)
        return method(node)

    @authenticator.auth(acl={'machine': set('X')})
    @audit()
    def start(self, machineId, **kwargs):
        """
        Start the machine

        :param machineId: id of the machine
        """
        return self._action(machineId, 'start', enums.MachineStatus.RUNNING)

    @authenticator.auth(acl={'machine': set('X')})
    @audit()
    def stop(self, machineId, **kwargs):
        """
        Stop the machine

        :param machineId: id of the machine
        """
        return self._action(machineId, 'stop', enums.MachineStatus.HALTED)

    @authenticator.auth(acl={'machine': set('X')})
    @audit()
    def reboot(self, machineId, **kwargs):
        """
        Reboot the machine

        :param machineId: id of the machine
        """
        return self._action(machineId, 'soft_reboot', enums.MachineStatus.RUNNING)

    @authenticator.auth(acl={'machine': set('X')})
    @audit()
    def reset(self, machineId, **kwargs):
        """
        Reset the machine, force reboot

        :param machineId: id of the machine
        """
        return self._action(machineId, 'hard_reboot', enums.MachineStatus.RUNNING)

    @authenticator.auth(acl={'machine': set('X')})
    @audit()
    def pause(self, machineId, **kwargs):
        """
        Pause the machine

        :param machineId: id of the machine
        """
        return self._action(machineId, 'pause', enums.MachineStatus.PAUSED)

    @authenticator.auth(acl={'machine': set('X')})
    @audit()
    def resume(self, machineId, **kwargs):
        """
        Resume the machine

        :param machineId: id of the machine
        """
        return self._action(machineId, 'resume', enums.MachineStatus.RUNNING)

    @authenticator.auth(acl={'machine': set('C')})
    @audit()
    def addDisk(self, machineId, diskName, description, size=10, type='D', **kwargs):
        """
        Create and attach a disk to the machine

        :param machineId: id of the machine
        :param diskName: name of disk
        :param description: optional description
        :param size: size in GByte default=10
        :param type: (B;D;T)  B=Boot;D=Data;T=Temp default=B
        :return int, id of the disk

        """
        machine = self._getMachine(machineId)
        cloudspace = self.models.cloudspace.get(machine.cloudspaceId)
        disk, volume = j.apps.cloudapi.disks._create(accountId=cloudspace.accountId, gid=cloudspace.gid,
                                    name=diskName, description=description, size=size, type=type, **kwargs)
        provider, node = self._getProviderAndNode(machineId)
        try:
            provider.client.attach_volume(node, volume)
        except:
            raise
        machine.disks.append(disk.id)
        self.models.vmachine.set(machine)
        return disk.id

    @authenticator.auth(acl={'machine': set('X')})
    @audit()
    def detachDisk(self, machineId, diskId, **kwargs):
        """
        Detach a disk from the machine

        :param machineId: id of the machine
        :param diskId: id of disk to detach
        :return: True if disk was detached successfully
        """
        diskId = int(diskId)
        machine = self._getMachine(machineId)
        if diskId not in machine.disks:
            return True
        provider, node = self._getProviderAndNode(machineId)
        disk = self.models.disk.get(int(diskId))
        volume = j.apps.cloudapi.disks.getStorageVolume(disk, provider, node)
        provider.client.detach_volume(volume)
        machine.disks.remove(diskId)
        self.models.vmachine.set(machine)
        return True

    @authenticator.auth(acl={'cloudspace': set('X')})
    @audit()
    def attachDisk(self, machineId, diskId, **kwargs):
        """
        Attach a disk to the machine

        :param machineId: id of the machine
        :param diskId: id of disk to attach
        :return: True if disk was attached successfully
        """
        diskId = int(diskId)
        machine = self._getMachine(machineId)
        if diskId in machine.disks:
            return True
        vmachines = self.models.vmachine.search({'disks': diskId})[1:]
        if vmachines:
            self.detachDisk(machineId=vmachines[0]['id'], diskId=diskId)
        disk = self.models.disk.get(int(diskId))
        provider, node = self._getProviderAndNode(machineId)
        volume = j.apps.cloudapi.disks.getStorageVolume(disk, provider, node)
        provider.client.attach_volume(node, volume)
        machine.disks.append(diskId)
        self.models.vmachine.set(machine)
        return True

    @authenticator.auth(acl={'account': set('C')})
    @audit()
    def createTemplate(self, machineId, templatename, basename, **kwargs):
        """
        Create a template from the active machine

        :param machineId: id of the machine
        :param templatename: name of the template
        :param basename: snapshot id on which the template is based
        :return True if template was created
        """
        machine = self._getMachine(machineId)
        node = self._getNode(machine.referenceId)
        provider = self._getProvider(machine)
        cloudspace = self.models.cloudspace.get(machine.cloudspaceId)
        image = self.models.image.new()
        image.name = templatename
        image.type = 'Custom Templates'
        m = {}
        m['stackId'] = machine.stackId
        m['disks'] = machine.disks
        m['sizeId'] = machine.sizeId
        firstdisk = self.models.disk.get(machine.disks[0])
        image.size = firstdisk.sizeMax
        image.username = ""
        image.accountId = cloudspace.accountId
        image.status = 'CREATING'
        imageid = self.models.image.set(image)[0]
        stack = self.models.stack.get(machine.stackId)
        stack.images.append(imageid)
        self.models.stack.set(stack)
        template = provider.client.ex_create_template(node, templatename, imageid, basename)
        return True

    @authenticator.auth(acl={'machine': set('X')})
    @audit()
    def backup(self, machineId, backupName, **kwargs):
        """
        backup is in fact an export of the machine to a cloud system close to the IAAS system on which the machine is running
        param:machineId id of machine to backup
        param:backupName name of backup
        result int

        """
        storageparameters = {'storage_type': 'ceph',
                             'bucket': 'vmbackup',
                             'mdbucketname': 'mdvmbackup'}

        return self._export(machineId, backupName, storageparameters)

    def _getProvider(self, machine):
        if machine.referenceId and machine.stackId:
            return self.cb.getProviderByStackId(machine.stackId)
        return None

    @authenticator.auth(acl={'cloudspace': set('C')})
    @audit()
    def create(self, cloudspaceId, name, description, sizeId, imageId, disksize, datadisks, **kwargs):
        """
        Create a machine based on the available sizes, in a certain cloud space
        The user needs write access rights on the cloud space

        :param cloudspaceId: id of cloud space in which we want to create a machine
        :param name: name of machine
        :param description: optional description
        :param sizeId: id of the specific size
        :param imageId: id of the specific image
        :param disksize: size of base volume
        :param datadisks: list of extra data disks
        :return bool

        """
        cloudspace = self.models.cloudspace.get(cloudspaceId)
        self.cb.machine.validateCreate(cloudspace, name, sizeId, imageId, disksize, self._minimum_days_of_credit_required)
        machine, auth, diskinfo = self.cb.machine.createModel(name, description, cloudspace, imageId, sizeId, disksize, datadisks)
        return self.cb.machine.create(machine, auth, cloudspace, diskinfo, imageId, None)

    @authenticator.auth(acl={'cloudspace': set('D')})
    @audit()
    def delete(self, machineId, **kwargs):
        """
        Delete the machine

        :param machineId: id of the machine
        :return True if machine was deleted successfully

        """
        provider, node = self._getProviderAndNode(machineId)
        if node and node.extra.get('locked', False):
            raise exceptions.Conflict("Can not delete a locked Machine")
        vmachinemodel = self._getMachine(machineId)
        self. _detachPublicNetworkFromModel(vmachinemodel)
        if not vmachinemodel.status == 'DESTROYED':
            vmachinemodel.deletionTime = int(time.time())
            vmachinemodel.status = 'DESTROYED'
            self.models.vmachine.set(vmachinemodel)

        tags = str(machineId)
        j.logger.log('Deleted', category='machine.history.ui', tags=tags)
        try:
            j.apps.cloudapi.portforwarding.deleteByVM(vmachinemodel)
        except Exception, e:
            j.errorconditionhandler.processPythonExceptionObject(e, message="Failed to delete portforwardings for vm with id %s" % machineId)

        if provider:
            for pnode in provider.client.list_nodes():
                if node.id == pnode.id:
                    provider.client.destroy_node(pnode)
                    break
        for disk in vmachinemodel.disks:
            j.apps.cloudapi.disks.delete(diskId=disk, detach=True)

        # delete leases
        cloudspace = self.models.cloudspace.get(vmachinemodel.cloudspaceId)
        fwid = "%s_%s" % (cloudspace.gid, cloudspace.networkId)
        macs = list()
        for nic in vmachinemodel.nics:
            if nic.type != 'PUBLIC' and nic.macAddress:
                macs.append(nic.macAddress)
        if macs:
            self.netmgr.fw_remove_lease(fwid, macs)
        return True


    @authenticator.auth(acl={'machine': set('R')})
    @audit()
    def get(self, machineId, **kwargs):
        """
        Get information from a certain object.
        This contains all information about the machine.
        param:machineId id of machine
        result

        """
        provider, node = self._getProviderAndNode(machineId)
        state = node.state
        machine = self._getMachine(machineId)
        disks = self.models.disk.search({'id': {'$in': machine.disks}})[1:]
        storage = sum(disk['sizeMax'] for disk in disks)
        osImage = self.models.image.get(machine.imageId).name
        if machine.nics and machine.nics[0].ipAddress == 'Undefined':
            if node.private_ips:
                machine.nics[0].ipAddress = node.private_ips[0]
            else:
                cloudspace = self.models.cloudspace.get(machine.cloudspaceId)
                fwid = "%s_%s" % (cloudspace.gid, cloudspace.networkId)
                try:
                    ipaddress = self.netmgr.fw_get_ipaddress(fwid, machine.nics[0].macAddress)
                    if ipaddress:
                        machine.nics[0].ipAddress = ipaddress
                        self.models.vmachine.set(machine)
                except exceptions.ServiceUnavailable:
                    pass # VFW not deployed yet

        realstatus = enums.MachineStatusMap.getByValue(state, provider.client.name) or state
        if realstatus != machine.status:
            if realstatus == 'DESTROYED':
                realstatus = 'HALTED'
            machine.status = realstatus
            self.models.vmachine.set(machine)
        acl = list()
        machine_acl = authenticator.auth().getVMachineAcl(machine.id)
        for _, ace in machine_acl.iteritems():
            acl.append({'userGroupId': ace['userGroupId'], 'type': ace['type'], 'canBeDeleted': ace['canBeDeleted'], 'right': ''.join(sorted(ace['right']))})
        return {'id': machine.id, 'cloudspaceid': machine.cloudspaceId, 'acl': acl, 'disks': disks,
                'name': machine.name, 'description': machine.descr, 'hostname': machine.hostName,
                'status': realstatus, 'imageid': machine.imageId, 'osImage': osImage, 'sizeid': machine.sizeId,
                'interfaces': machine.nics, 'storage': storage, 'accounts': machine.accounts, 'locked': node.extra.get('locked', False)}

    @audit()
    def list(self, cloudspaceId, status=None, **kwargs):
        """
        List the deployed machines in a space. Filtering based on status is possible
        :param cloudspaceId: id of cloud space in which machine exists @tags: optional
        :param status: when not empty will filter on type (types are ACTIVE,HALTED,BACKUP,EXPORT,SNAPSHOT)
        :return list of dict with each element containing the machine details

        """
        ctx = kwargs['ctx']
        if not cloudspaceId:
            raise exceptions.BadRequest('Please specify a cloudsapce ID.')
        cloudspaceId = int(cloudspaceId)
        fields = ['id', 'referenceId', 'cloudspaceid', 'hostname', 'imageId', 'name', 'nics', 'sizeId', 'status', 'stackId', 'disks']

        user = ctx.env['beaker.session']['user']
        userobj = j.core.portal.active.auth.getUserInfo(user)
        groups = userobj.groups
        cloudspace = self.models.cloudspace.get(cloudspaceId)
        auth = authenticator.auth()
        acl = auth.expandAclFromCloudspace(user, groups, cloudspace)
        q = {"cloudspaceId": cloudspaceId, "status": {"$ne": "DESTROYED"}}
        if 'R' not in acl and 'A' not in acl:
            q['acl.userGroupId'] = user

        query = {'$query': q, '$fields': fields}
        results = self.models.vmachine.search(query)[1:]
        machines = []
        alldisks = list(itertools.chain(*[m['disks'] for m in results]))
        query = {'$query': {'id': {'$in': alldisks}}, '$fields': ['id', 'sizeMax']}
        disks = {disk['id']: disk.get('sizeMax', 0) for disk in self.models.disk.search(query)[1:]}
        for res in results:
            size = sum(disks.get(diskid, 0) for diskid in res['disks'])
            res['storage'] = size
            machines.append(res)
        return machines

    def _getMachine(self, machineId):
        machineId = int(machineId)
        return self.models.vmachine.get(machineId)

    def _getNode(self, referenceId):
        return self.cb.Dummy(id=referenceId)

    def _getProviderAndNode(self, machineId):
        machineId = int(machineId)
        machine = self._getMachine(machineId)
        provider = self._getProvider(machine)
        if provider:
            node = provider.client.ex_get_node_details(machine.referenceId)
        else:
            node = None
        return provider, node

    @authenticator.auth(acl={'machine': set('C')})
    @audit()
    def snapshot(self, machineId, name, **kwargs):
        """
        Take a snapshot of the machine

        :param machineId: id of the machine to snapshot
        :param name: name to give snapshot
        :return the snapshot name
        """
        provider, node = self._getProviderAndNode(machineId)
        snapshots = provider.client.ex_list_snapshots(node)
        if len(snapshots) > 5:
            raise exceptions.Conflict('Max 5 snapshots allowed')
        node = provider.client.ex_get_node_details(node.id)
        if node.extra.get('locked', False):
            raise exceptions.Conflict('Cannot create snapshot on a locked machine')
        tags = str(machineId)
        j.logger.log('Snapshot created', category='machine.history.ui', tags=tags)
        snapshot = provider.client.ex_create_snapshot(node, name)
        return snapshot['name']

    @authenticator.auth(acl={'machine': set('R')})
    @audit()
    def listSnapshots(self, machineId, **kwargs):
        """
        List the snapshots of the machine

        :param machineId: id of the machine
        :return: list with the available snapshots
        """
        provider, node = self._getProviderAndNode(machineId)
        node.name = 'vm-%s' % machineId
        snapshots = provider.client.ex_list_snapshots(node)
        result = []
        for snapshot in snapshots:
            if snapshot['name'] and not snapshot['name'].endswith('_DELETING'):
                result.append(snapshot)
        return result

    @authenticator.auth(acl={'machine': set('X')})
    @audit()
    def deleteSnapshot(self, machineId, epoch, **kwargs):
        """
        Delete a snapshot of the machine

        :param machineId: id of the machine
        :param epoch: epoch time of snapshot
        """
        provider, node = self._getProviderAndNode(machineId)
        tags = str(machineId)
        j.logger.log('Snapshot deleted', category='machine.history.ui', tags=tags)
        return provider.client.ex_delete_snapshot(node, epoch)

    @authenticator.auth(acl={'machine': set('X')})
    @audit()
    @RequireState(enums.MachineStatus.HALTED, 'A snapshot can only be rolled back to a stopped Machine')
    def rollbackSnapshot(self, machineId, epoch, **kwargs):
        """
        Rollback a snapshot of the machine

        :param machineId: id of the machine
        :param epoch: epoch time of snapshot
        """
        provider, node = self._getProviderAndNode(machineId)
        tags = str(machineId)
        j.logger.log('Snapshot rolled back', category='machine.history.ui', tags=tags)
        return provider.client.ex_rollback_snapshot(node, epoch)

    @authenticator.auth(acl={'machine': set('C')})
    @audit()
    def update(self, machineId, name=None, description=None, size=None, **kwargs):
        """
        Change basic properties of a machine
        Name, description can be changed with this action.

        :param machineId: id of the machine
        :param name: name of the machine
        :param description: description of the machine
        :param size: size of the machine in CU

        """
        machine = self._getMachine(machineId)
        #if name:
        #    if not self._assertName(machine.cloudspaceId, name, **kwargs):
        #        ctx = kwargs['ctx']
        #        ctx.start_response('409 Conflict', [])
        #        return 'Selected name already exists'
        #    machine.name = name
        if description:
            machine.descr = description
        #if size:
        #    machine.nrCU = size
        return self.models.vmachine.set(machine)[0]

    @authenticator.auth(acl={'machine': set('R')})
    @audit()
    def getConsoleUrl(self, machineId, **kwargs):
        """
        Get url to connect to console

        :param machineId: id of the machine to connect to console
        :return one time url used to connect ot console

        """
        machine = self._getMachine(machineId)
        if machine.status != enums.MachineStatus.RUNNING:
            return None
        provider, node = self._getProviderAndNode(machineId)
        return provider.client.ex_get_console_url(node)

    @authenticator.auth(acl={'cloudspace': set('C')})
    @audit()
    @RequireState(enums.MachineStatus.HALTED, 'A clone can only be taken from a stopped machine bucket')
    def clone(self, machineId, name, **kwargs):
        """
        Clone the machine

        :param machineId: id of the machine to clone
        :param name: name of the cloned machine
        :return id of the new cloned machine
        """
        machine = self._getMachine(machineId)
        cloudspace = self.models.cloudspace.get(machine.cloudspaceId)
        if machine.cloneReference:
            raise exceptions.MethodNotAllowed('Cannot clone a cloned machine.')

        if not self.cb.machine._assertName(machine.cloudspaceId, name, **kwargs):
            raise exceptions.Conflict('Selected name already exists')
        clone = self.models.vmachine.new()
        clone.cloudspaceId = machine.cloudspaceId
        clone.name = name
        clone.descr = machine.descr
        clone.sizeId = machine.sizeId
        clone.imageId = machine.imageId
        clone.cloneReference = machine.id
        clone.acl = machine.acl
        clone.creationTime = int(time.time())

        diskmapping = []
        for diskId in machine.disks:
            origdisk = self.models.disk.get(diskId)
            clonedisk = self.models.disk.new()
            clonedisk.name = origdisk.name
            clonedisk.gid = origdisk.gid
            clonedisk.order = origdisk.order
            clonedisk.accountId = origdisk.accountId
            clonedisk.type = origdisk.type
            clonedisk.descr = origdisk.descr
            clonedisk.sizeMax = origdisk.sizeMax
            clonediskId = self.models.disk.set(clonedisk)[0]
            clone.disks.append(clonediskId)
            diskmapping.append({'origId': diskId, 'cloneId': clonediskId,
                                'size': origdisk.sizeMax, 'type': clonedisk.type,
                                'diskpath': origdisk.referenceId})
        clone.id = self.models.vmachine.set(clone)[0]
        provider, node = self._getProviderAndNode(machineId)
        size = self.cb.machine.getSize(provider, clone)
        node = provider.client.ex_clone(node, size, clone.id, cloudspace.networkId, diskmapping)
        self.cb.machine.updateMachineFromNode(clone, node, machine.stackId, size)
        tags = str(machineId)
        j.logger.log('Cloned', category='machine.history.ui', tags=tags)
        return clone.id

    @authenticator.auth(acl={'machine': set('R')})
    @audit()
    def getHistory(self, machineId, size, **kwargs):
        """
        Get machine history

        :param machineId: id of the machine
        :param size: number of entries to return
        :return: list of the history of the machine
        """
        tags = str(machineId)
        query = {'category': 'machine_history_ui', 'tags': tags}
        return self.osis_logs.search(query, size=size)[1:]

    @authenticator.auth(acl={'machine': set('C')})
    @audit()
    def export(self, machineId, name, host, aws_access_key, aws_secret_key, bucket, **kwargs):
        """
        Create an export/backup of the machine

        :param machineId: id of the machine to backup
        :param name: useful name for this backup
        :param host: host to export(if s3)
        :param aws_access_key: s3 access key
        :param aws_secret_key: s3 secret key
        :param bucket: s3 bucket name
        :return: jobid
        """
        storageparameters = {}
        if not aws_access_key or not aws_secret_key or not host:
            raise exceptions.BadRequest('S3 parameters are not provided')
        storageparameters['aws_access_key'] = aws_access_key
        storageparameters['aws_secret_key'] = aws_secret_key
        storageparameters['host'] = host
        storageparameters['is_secure'] = True

        storageparameters['storage_type'] = 'S3'
        storageparameters['backup_type'] = 'condensed'
        storageparameters['bucket'] = bucket
        storageparameters['mdbucketname'] = bucket
        return self._export(machineId, name, host, storageparameters)

    def _export(self, machineId, name, storageparameters, **kwargs):
        """
        Create a export/backup of a machine

        :param machineId: id of the machine to backup
        :param name: useful name for this backup
        :param backuptype: Type e.g raw, condensed
        :param host: host to export(if s3)
        :param aws_access_key: s3 access key
        :param aws_secret_key: s3 secret key
        :return jobid
        """
        system_cl = j.clients.osis.getNamespace('system')
        machine = self.models.vmachine.get(machineId)
        if not machine:
            raise exceptions.NotFound('Machine %s not found' % machineId)
        stack = self.models.stack.get(machine.stackId)

        storagepath = '/mnt/vmstor/vm-%s' % machineId
        nid = int(stack.referenceId)
        args = {'path':storagepath, 'name':name, 'machineId':machineId, 'storageparameters': storageparameters,'nid':nid, 'backup_type':'condensed'}
        agentcontroller = j.clients.agentcontroller.get()
        id = agentcontroller.executeJumpscript('cloudscalers', 'cloudbroker_export', j.application.whoAmI.nid, args=args, wait=False)['id']
        return id

    @authenticator.auth(acl={'cloudspace': set('X')})
    @audit()
    def importToNewMachine(self, name, cloudspaceId, vmexportId, sizeId, description, aws_access_key, aws_secret_key, **kwargs):
        """
        Restore export to a new machine

        :param name: name of the machine
        :param cloudspaceId: id of the export to backup
        :param sizeId: id of the specific size
        :param description: optional description
        :param aws_access_key: s3 access key
        :param aws_secret_key: s3 secret key
        :return jobid
        """
        vmexport = self.models.vmexport.get(vmexportId)
        if not vmexport:
            raise exceptions.NotFound('Export definition with id %s not found' % vmexportId)
        host = vmexport.server
        bucket = vmexport.bucket
        import_name = vmexport.name

        storageparameters = {}

        if not aws_access_key or not aws_secret_key:
            raise exceptions.BadRequest('S3 parameters are not provided')

        storageparameters['aws_access_key'] = aws_access_key
        storageparameters['aws_secret_key'] = aws_secret_key
        storageparameters['host'] = host
        storageparameters['is_secure'] = True

        storageparameters['storage_type'] = 'S3'
        storageparameters['backup_type'] = 'condensed'
        storageparameters['bucket'] = bucket
        storageparameters['mdbucketname'] = bucket
        storageparameters['import_name'] = import_name

        args = {'name':name, 'cloudspaceId':cloudspaceId, 'vmexportId':vmexportId, 'sizeId':sizeId, 'description':description, 'storageparameters': storageparameters}

        agentcontroller = j.clients.agentcontroller.get()

        id = agentcontroller.executeJumpscript('cloudscalers', 'cloudbroker_import_tonewmachine', j.application.whoAmI.nid, args=args, wait=False)['id']
        return id

    @authenticator.auth(acl={'machine': set('R')})
    @audit()
    def listExports(self, machineId, status, **kwargs):
        """
        List exported images

        :param machineId: id of the machine
        :param status: filter on specific status
        :return list of exports, each as a dict
        """
        query = {}
        if status:
            query['status'] = status
        if machineId:
            query['machineId'] = machineId
        exports = self.models.vmexport.search(query)[1:]
        exportresult = []
        for exp in exports:
            exportresult.append({'status':exp['status'], 'type':exp['type'], 'storagetype':exp['storagetype'], 'machineId': exp['machineId'], 'id':exp['id'], 'name':exp['name'],'timestamp':exp['timestamp']})
        return exportresult

    @authenticator.auth(acl={'cloudspace': set('X'), 'machine': set('U')})
    @audit()
    def addUser(self, machineId, userId, accesstype, **kwargs):
        """
        Give a registered user access rights

        :param machineId: id of the machine
        :param userId: username or emailaddress of the user to grant access
        :param accesstype: 'R' for read only access, 'RCX' for Write and 'ARCXDU' for Admin
        :return True if user was added successfully
        """
        user = self.cb.checkUser(userId)
        if not user:
            raise exceptions.NotFound("User is not registered on the system")
        else:
            # Replace email address with ID
            userId = user['id']

        return self._addACE(machineId, userId, accesstype, userstatus='CONFIRMED')

    @authenticator.auth(acl={'cloudspace': set('X'), 'machine': set('U')})
    @audit()
    def addExternalUser(self, machineId, emailaddress, accesstype, **kwargs):
        """
        Give an unregistered user access rights by sending an invite email

        :param machineId: id of the machine
        :param emailaddress: emailaddress of the unregistered user that will be invited
        :param accesstype: 'R' for read only access, 'RCX' for Write and 'ARCXDU' for Admin
        :return True if user was added successfully
        """
        if self.systemodel.user.search({'emails': emailaddress})[1:]:
            raise exceptions.BadRequest('User is already registered on the system, please add as '
                                        'a normal user')

        self._addACE(machineId, emailaddress, accesstype, userstatus='INVITED')
        try:
            j.apps.cloudapi.users.sendInviteLink(emailaddress, 'machine', machineId, accesstype)
            return True
        except:
            self.deleteUser(machineId, emailaddress)
            raise

    def _addACE(self, machineId, userId, accesstype, userstatus='CONFIRMED'):
        """
        Add a new ACE to the ACL of the vmachine
        :param:machineId id of the vmachine
        :param userId: userid for registered users or emailaddress for unregistered users
        :param accesstype: 'R' for read only access, 'W' for Write access
        :param userstatus: status of the user (CONFIRMED or INVITED)
        :return True if ACE was successfully added
        """
        machineId = int(machineId)
        vmachine = self.models.vmachine.get(machineId)
        vmachine_acl = authenticator.auth().getVMachineAcl(machineId)
        if userId in vmachine_acl:
            return self._updateACE(machineId, userId, accesstype, userstatus)

        ace = vmachine.new_acl()
        ace.userGroupId = userId
        ace.type = 'U'
        ace.right = accesstype
        ace.status = userstatus
        self.models.vmachine.set(vmachine)
        return True

    def _updateACE(self, machineId, userId, accesstype, userstatus):
        """
        Update an existing ACE in the ACL of a machine
        :param machineId: id of the cloudspace
        :param userId: userid for registered users or emailaddress for unregistered users
        :param accesstype: 'R' for read only access, 'W' for Write access
        :param userstatus: status of the user (CONFIRMED or INVITED)
        :return True if ACE was successfully updated, False if no update is needed
        """
        machineId = int(machineId)
        vmachine = self.models.vmachine.get(machineId)
        vmachine_acl = authenticator.auth().getVMachineAcl(machineId)
        if userId in vmachine_acl:
            useracl = vmachine_acl[userId]
        else:
            raise exceptions.NotFound('User does not have any access rights to update')

        if ('account_right' in useracl and set(accesstype) == set(useracl['account_right'])) or \
                ('cloudspace_right' in useracl and
                    set(accesstype) == set(useracl['cloudspace_right'])):
            # Remove machine level access rights if present
            for ace in vmachine.acl:
                if ace.userGroupId == userId and ace.type == 'U':
                    vmachine.acl.remove(ace)
                    self.models.vmachine.set(vmachine)
                    break
            return False
        # If user has higher access rights on owning account level then do not update
        if 'account_right' in useracl and set(accesstype) != set(useracl['account_right']) and \
                set(accesstype).issubset(set(useracl['account_right'])):
            raise exceptions.Conflict('User already has a higher access level to owning account')
        # If user has higher access rights on cloudspace then do not update
        elif 'cloudspace_right' in useracl and set(accesstype) != set(useracl['cloudspace_right']) \
                and set(accesstype).issubset(set(useracl['cloudspace_right'])):
            raise exceptions.Conflict('User already has a higher access level to cloudspace')
        else:
            # grant higher access level
            for ace in vmachine.acl:
                if ace.userGroupId == userId and ace.type == 'U':
                    ace.right = accesstype
                    break
            else:
                ace = vmachine.new_acl()
                ace.userGroupId = userId
                ace.type = 'U'
                ace.right = accesstype
                ace.status = userstatus
            self.models.vmachine.set(vmachine)
        return True

    @authenticator.auth(acl={'cloudspace': set('X'), 'machine': set('U')})
    @audit()
    def deleteUser(self, machineId, userId, **kwargs):
        """
        Revoke user access from the vmachine

        :param machineId: id of the machine
        :param userId: id or emailaddress of the user to remove
        :return True if user access was revoked from machine
        """
        machineId = int(machineId)
        vmachine = self.models.vmachine.get(machineId)
        for ace in vmachine.acl[:]:
            if ace.userGroupId == userId:
                vmachine.acl.remove(ace)
                self.models.vmachine.set(vmachine)
                return True

        # User was not found in access rights
        raise exceptions.NotFound('User with the username/emailaddress %s does not have access '
                                  'on the machine' % userId)

    @authenticator.auth(acl={'cloudspace': set('X'), 'machine': set('U')})
    @audit()
    def updateUser(self, machineId, userId, accesstype, **kwargs):
        """
        Update user access rights

        :param machineId: id of the machineId
        :param userId: userid/email for registered users or emailaddress for unregistered users
        :param accesstype: 'R' for read only access, 'RCX' for Write and 'ARCXDU' for Admin
        :return True if user access was updated successfully
        """
        # Check if user exists in the system or is an unregistered invited user
        existinguser = self.systemodel.user.search({'id': userId})[1:]
        if existinguser:
            userstatus = 'CONFIRMED'
        else:
            userstatus = 'INVITED'
        return self._updateACE(machineId, userId, accesstype, userstatus)

    @authenticator.auth(acl={'cloudspace': set('X')})
    def attachPublicNetwork(self, machineId, **kwargs):
        """
         Attach a public network to the machine

        :param machineId: id of the machine
        :return: True if a public network was attached to the machine
        """
        provider, node = self._getProviderAndNode(machineId)
        vmachine = self._getMachine(machineId)
        for nic in vmachine.nics:
            if nic.type == 'PUBLIC':
                return True
        cloudspace = self.models.cloudspace.get(vmachine.cloudspaceId)
        networkid = cloudspace.networkId
        netinfo = self.network.getPublicIpAddress(cloudspace.gid)
        if netinfo is None:
            raise RuntimeError("No available public IPAddresses")
        pool, publicipaddress = netinfo
        if not publicipaddress:
            raise RuntimeError("Failed to get publicip for networkid %s" % networkid)
        nic = vmachine.new_nic()
        nic.ipAddress = str(publicipaddress)
        nic.params = j.core.tags.getTagString([], {'gateway': pool.gateway})
        nic.type = 'PUBLIC'
        self.models.vmachine.set(vmachine)
        iface = provider.client.attach_public_network(node)
        nic.deviceName = iface.target
        nic.macAddress = iface.mac
        self.models.vmachine.set(vmachine)
        return True

    @authenticator.auth(acl={'cloudspace': set('X')})
    def detachPublicNetwork(self, machineId, **kwargs):
        """
        Detach the public network from the machine

        :param machineId: id of the machine
        :return: True if public network was detached from the machine
        """
        provider, node = self._getProviderAndNode(machineId)
        vmachine = self._getMachine(machineId)
        cloudspace = self.models.cloudspace.get(vmachine.cloudspaceId)
        networkid = cloudspace.networkId
        
        for nic in vmachine.nics:
            nicdict = nic.obj2dict()
            if 'type' not in nicdict or nicdict['type'] != 'PUBLIC':
                continue
            
            provider.client.detach_public_network(node, networkid)
        self._detachPublicNetworkFromModel(vmachine)
        return True

    def _detachPublicNetworkFromModel(self, vmachine):
        for nic in vmachine.nics:
            nicdict = nic.obj2dict()
            if 'type' not in nicdict or nicdict['type'] != 'PUBLIC':
                continue
            vmachine.nics.remove(nic)
            self.models.vmachine.set(vmachine)
            self.network.releasePublicIpAddress(nic.ipAddress)
