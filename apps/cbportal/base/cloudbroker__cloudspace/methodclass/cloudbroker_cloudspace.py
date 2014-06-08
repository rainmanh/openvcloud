from JumpScale import j
import JumpScale.grid.osis
from JumpScale.portal.portal.auth import auth

class cloudbroker_cloudspace(j.code.classGetBase()):
    def __init__(self):
        self._te={}
        self.actorname="cloudspace"
        self.appname="cloudbroker"
        self.cbcl = j.core.osis.getClientForNamespace('cloudbroker')

    @auth(['level1', 'level2'])
    def destroy(self, accountname, cloudspaceName, cloudspaceId, reason, **kwargs):
        accounts = self.cbcl.account.simpleSearch({'name':accountname})
        if not accounts:
            ctx = kwargs["ctx"]
            headers = [('Content-Type', 'application/json'), ]
            ctx.start_response("404", headers)
            return 'Account name not found'

        accountid = accounts[0]['id']

        cloudspaces = self.cbcl.cloudspace.simpleSearch({'name': cloudspaceName, 'id': cloudspaceId, 'accountId': accountid})
        if not cloudspaces:
            ctx = kwargs["ctx"]
            headers = [('Content-Type', 'application/json'), ]
            ctx.start_response("404", headers)
            return 'Cloudspace with name %s and id %s that has account %s not found' % (cloudspaceName, cloudspaceId, accountname)

        cloudspace = cloudspaces[0]

        if str(cloudspace['location']) != j.application.config.get('cloudbroker.where.am.i'):
            ctx = kwargs["ctx"]
            headers = [('Content-Type', 'application/json'), ('Location', '')]
            ctx.start_response("302", headers)
            return "Cloudspace can not be destroyed. It's on a different location %s" % cloudspace['location']

        cloudspace['status'] = 'DESTROYED'
        self.cbcl.cloudspace.set(cloudspace)
        #DESTROY ROUTER OS + release networkId and publicip
