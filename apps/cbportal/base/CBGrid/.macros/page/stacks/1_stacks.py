
def main(j, args, params, tags, tasklet):

    page = args.page
    modifier = j.html.getPageModifierGridDataTables(page)

    imageid = args.getTag("imageid")
    filters = dict()

    if imageid:
        args.tags.tags.pop('imageid')
        imageid = str(imageid)
        ccl = j.core.osis.getClientForNamespace('cloudbroker')
        images = ccl.image.search({'referenceId': imageid})[1:]
        if images:
            filters['images'] = images[0]['id']

    for tag, val in args.tags.tags.iteritems():
        val = args.getTag(tag)
        if val:
            filters[tag] = j.basetype.integer.fromString(val) if j.basetype.integer.checkString(val) else val

    fieldnames = ['Grid ID', 'ID', 'Name', 'Reference ID', 'Type', 'Description']
    fieldvalues = ["<a href='/cbgrid/grid?gid=%(gid)s'>%(gid)s</a>", "<a href='/cbgrid/stack?id=%(id)s'>%(id)s</a>", "name", 'referenceId', 'type', 'descr']
    fieldids = ['gid', 'id', 'name', 'referenceId', 'type', 'descr']
    tableid = modifier.addTableForModel('cloudbroker', 'stack', fieldids, fieldnames, fieldvalues, filters)
    modifier.addSearchOptions('#%s' % tableid)

    params.result = page
    return params


def match(j, args, params, tags, tasklet):
    return True