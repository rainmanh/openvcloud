from JumpScale import j
from cloudapi_cloudspaces_osis import cloudapi_cloudspaces_osis
from cloudbrokerlib import authenticator


class cloudapi_cloudspaces(cloudapi_cloudspaces_osis):

    """
    API Actor api for managing cloudspaces, this actor is the final api a enduser uses to manage cloudspaces

    """

    def __init__(self):

        self._te = {}
        self.actorname = "cloudspaces"
        self.appname = "cloudapi"
        cloudapi_cloudspaces_osis.__init__(self)
        self._cb = None

    @property
    def cb(self):
        if not self._cb:
            self._cb = j.apps.cloud.cloudbroker
        return self._cb

    @authenticator.auth(acl='U')
    def addUser(self, cloudspaceId, userId, accesstype, **kwargs):
        """
        Give a user access rights.
        Access rights can be 'R' or 'W'
        params:cloudspaceId id of the cloudspace
        param:userId id of the user to give access
        param:accesstype 'R' for read only access, 'W' for Write access
        result bool

        """
        cs = self.cb.models.cloudspace.new()
        cloudspace = self.cb.model_cloudspace_get(cloudspaceId)
        cs.dict2obj(cloudspace)
        acl = cs.new_acl()
        acl.userGroupId = userId
        acl.type = 'U'
        acl.right = accesstype
        return self.cb.models.cloudspace.set(cs.obj2dict())

    @authenticator.auth(acl='A')
    def create(self, accountId, name, access, maxMemoryCapacity, maxDiskCapacity, **kwargs):
        """
        Create a extra cloudspace
        param:name name of space to create
        param:access list of ids of users which have full access to this space
        param:maxMemoryCapacity max size of memory in space (in GB)
        param:maxDiskCapacity max size of aggregated disks (in GB)
        result int

        """
        cs = self.cb.models.cloudspace.new()
        cs.name = name
        cs.accountId = accountId
        for userid in access:
            ace = cs.new_acl()
            ace.userGroupId = userid
            ace.type = 'U'
            ace.right = 'CXDRAU'
        cs.resourceLimits['CU'] = maxMemoryCapacity
        cs.resourceLimits['SU'] = maxDiskCapacity
        return self.cb.models.cloudspace.set(cs.obj2dict())

    @authenticator.auth(acl='A')
    def delete(self, cloudspaceId, **kwargs):
        """
        Delete a cloudspace.
        param:cloudspaceId id of the cloudspace
        result bool,

        """
        return self.cb.model_cloudspace_delete(cloudspaceId)

    def get(self, cloudspaceId, **kwargs):
        """
        get cloudspaces.
        param:cloudspaceId id of the cloudspace
        result dict
        """
        #put your code here to implement this method
        return self.cb.model_cloudspace_get(cloudspaceId)

    @authenticator.auth(acl='U')
    def deleteUser(self, cloudspaceId, userId, **kwargs):
        """
        Delete a user from the cloudspace
        params:cloudspaceId id of the cloudspace
        param:userId id of the user to remove
        result

        """
        cloudspace = self.cb.model_cloudspace_get(cloudspaceId)
        change = False
        for ace in cloudspace['acl'][:]:
            if ace['userGroupId'] == userId:
                cloudspace['acl'].remove(ace)
                change = True
        if change:
            self.cb.models.cloudspace.set(cloudspace)
        return change

    def list(self, **kwargs):
        """
        List cloudspaces.
        result [],

        """
#TODO implement dynamic filter here based on user access
        return self.cb.model_cloudspace_list()

    @authenticator.auth(acl='A')
    def update(self, cloudspaceId, name, maxMemoryCapacity, maxDiskCapacity, **kwargs):
        """
        Update a cloudspace name and capacity parameters can be updated
        param:cloudspaceId id of the cloudspace to change
        param:name name of the cloudspace
        param:maxMemoryCapacity max size of memory in space(in GB)
        param:maxDiskCapacity max size of aggregated disks(in GB)
        result int

        """
        # put your code here to implement this method
        raise NotImplementedError("not implemented method update")