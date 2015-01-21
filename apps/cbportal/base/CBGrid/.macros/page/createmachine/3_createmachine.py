from JumpScale.portal.docgenerator.popup import Popup

def main(j, args, params, tags, tasklet):
    params.result = page = args.page
    cloudspaceId = int(args.getTag('cloudspaceId'))
    scl = j.core.osis.getClientForNamespace('cloudbroker')
    actors = j.apps.cloudbroker.iaas.cb.actors.cloudapi

    cloudspace = scl.cloudspace.get(cloudspaceId)
    stacks = scl.stack.search({'gid': cloudspace.gid, 'status': 'ENABLED'})[1:]

    sizes = scl.size.search({})[1:]
    images = actors.images.list(cloudspace.accountId)
    dropsizes = list()
    dropdisksizes = list()
    dropimages = list()
    dropstacks = list()
    def sizeSorter(size):
        return size['memory']

    def imageSorter(image):
        return image['type'] + image['name']

    def sortName(item):
        return item['name']

    for image in sorted(images, key=imageSorter):
        dropimages.append(("%(type)s: %(name)s" % image, image['id']))

    for size in sorted(sizes, key=sizeSorter):
        dropsizes.append(("%(memory)s MB" % size, size['id']))

    for size in (10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100):
        dropdisksizes.append(("%s GB" % size, str(size)))

    for stack in sorted(stacks, key=sortName):
        dropstacks.append((stack['name'], stack['id']))


    popup = Popup(id='createmachine', header='Create Machine', submit_url='/restmachine/cloudbroker/machine/create')
    popup.addText('Machine Name', 'name', required=True)
    popup.addText('Machine Description', 'description', required=True)
    popup.addDropdown('Choose Image', 'imageId', dropimages)
    popup.addDropdown('Choose Memory', 'sizeId', dropsizes)
    popup.addDropdown('Choose Disk Size', 'disksize', dropdisksizes)
    popup.addHiddenField('cloudspaceId', cloudspaceId)
    popup.write_html(page)

    popup = Popup(id='createmachineonstack', header='Create Machine On Stack', submit_url='/restmachine/cloudbroker/machine/createOnStack')
    popup.addText('Machine Name', 'name', required=True)
    popup.addText('Machine Description', 'description', required=True)
    popup.addDropdown('Choose Stack', 'stackid', dropstacks)
    popup.addDropdown('Choose Image', 'imageId', dropimages)
    popup.addDropdown('Choose Memory', 'sizeId', dropsizes)
    popup.addDropdown('Choose Disk Size', 'disksize', dropdisksizes)
    popup.addHiddenField('cloudspaceId', cloudspaceId)
    popup.write_html(page)

    return params


def match(j, args, params, tags, tasklet):
    return True