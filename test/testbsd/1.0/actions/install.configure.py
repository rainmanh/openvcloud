def main(j,jp):
    from JumpScale import j
    import JumpScale.grid.osis
    import requests
    #register image on cloudbroker


    node_id = '$(cloudscalers.compute.nodeid)'

    secret = '$(cloudscalers.cloudbroker.secret)'
    serverip = j.application.config.get("grid.master.ip")
    auth = {'authkey': secret}
    
    if serverip=="":
        raise RuntimeError("grid.master.ip found but not filled in")

    url = "http://%s/restmachine/cloud/cloudbroker/updateImages" % serverip
    listimagesurl = "http://%s/restmachine/libcloud/libvirt/listImages" % serverip

    image_id = str(int(j.tools.hash.md5_string(jp.name)[0:9], 16))
    name = 'freebsdtest'

    osiscl = j.core.osis.getClient(serverip, user='root')

    catimageclient = j.core.osis.getClientForCategory(osiscl, 'libvirt', 'image')
    catresourceclient = j.core.osis.getClientForCategory(osiscl, 'libvirt', 'resourceprovider')


    imagepath = 'testbsd.qcow2'
    requests.post(listimagesurl, auth).json()
    installed_images = catimageclient.list()
    if image_id not in installed_images:
        image = dict()
        image['name'] = name
        image['id'] = image_id
        image['UNCPath'] = imagepath
        image['type'] = 'Linux'
        image['size'] = 10
        catimageclient.set(image)

    id = node_id

    if not id in catresourceclient.list():
        rp = dict()
        rp['cloudUnitType'] = 'CU'
        rp['id'] = id
        rp['images'] = [image_id]
    else:
        rp = catresourceclient.get(id)
        if not image_id in rp.images:
            rp.images.append(image_id)
    catresourceclient.set(rp)


    requests.post(url, auth).json()
    return True