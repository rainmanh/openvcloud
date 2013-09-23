defineApiStub = function ($httpBackend) {


    $httpBackend.whenGET(/^partials\//).passThrough();


    $httpBackend.whenPOST('/users/authenticate').
    respond(function (method, url, data) {
        var credentials = angular.fromJson(data);
        if (credentials.username == 'error') {
            return [403, 'Unauthorized'];
        }
        return [200, "yep123456789"];
    });

    var cloudspaces = [{
        'id': 0,
        'name': 'Main cloudspace',
        'description': 'Description'
    }, {
        'id': 1,
        'name': 'Production cloudspace',
        'description': 'Production Cloudspace'
    }];

    var machines = [{
        "status": "RUNNING",
        "hostname": "jenkins.cloudscalers.com",
        "description": "JS Webserver",
        "name": "CloudScalers Jenkins",
        "nics": [],
        "sizeId": 0,
        "imageId": 0,
        "id": 0
    }, {
        "status": "HALTED",
        "hostname": "cloudbroker.cloudscalers.com",
        "description": "CloudScalers CloudBroker",
        "name": "CloudBroker",
        "nics": [],
        "sizeId": 0,
        "imageId": 1,
        "id": 1
    }];

    var images = [{
        'id': 0,
        'name': 'Linux',
        'description': 'An ubuntu 13.04 image',
        "type": "Ubuntu"
    }, {
        'id': 1,
        'name': 'Windows',
        'description': 'A windows 2012 server',
        "type": "Windows"
    }];

    var sizes = [{
        'id': 0,
        'name': 'Small',
        'CU': 1,
        'disksize': 20
    }, {
        'id': 1,
        'name': 'Medium',
        'CU': 2,
        'disksize': 40
    }, {
        'id': 2,
        'name': 'Big',
        'CU': 4,
        'disksize': 100
    }];

    var actionlist = {
        'stop': 'HALTED',
        'start': 'RUNNING'
    };


    $httpBackend.whenGET(/^\/machines\/get\?authkey=yep123456789&machineId=(.+)/).respond(function (method, url, data) {
        var matches = /^\/machines\/get\?authkey=yep123456789&machineId=(.+)/.exec(url);
        var requestedId = matches[1];
        if (!_.has(machines, requestedId)) {
            return [500, 'Not found']
        }
        var matchedMachine = machines[requestedId];
        return [200, matchedMachine];
    });

    $httpBackend.whenGET('/machines/list?authkey=yep123456789' + '&cloudspaceId=' + 0 + '&type=').respond(function (method, url, data) {
        return [200, _.values(machines)];
    });
    $httpBackend.whenGET('/images/list?authkey=yep123456789').respond(images);
    $httpBackend.whenGET('/sizes/list?authkey=yep123456789').respond(sizes);
    $httpBackend.whenGET(/^\/machines\/create\?authkey\=yep123456789/).respond(function (method, url, data) {
        var params = new URI(url).search(true);
        var id = _.keys(machines).length;
        var machine = {
            "status": "RUNNING",
            "cloudspaceId": params.cloudspaceId,
            "hostname": params.name,
            "description": params.description,
            "name": params.name,
            "nics": [],
            "sizeId": params.sizeId,
            "imageId": params.imageId,
            "id": id
        };
        machines[id] = machine;
        return [200, id];

    });
    $httpBackend.whenGET(/^\/machines\/action\?authkey\=yep123456789/).respond(function (method, url, data) {
        var params = new URI(url).search(true);
        var action = params.action;
        var machineid = params.machineId;
        if (!_.has(actionlist, action)) {
            return [500, 'Invallid action'];
        }
        machine = machines[machineid];
        machine.status = actionlist[action];
        machines[machineid] = machine;
        return [200, true];
    });

    $httpBackend.whenGET(/^\/machines\/delete\?authkey\=yep123456789/).respond(function (method, url, data) {
        var params = new URI(url).search(true);
        var machineid = params.machineId;
        console.log('Stub Delete');
        console.log(machineid);
        if (!_.has(machines, machineid)) {
            return [500, 'Machine not found'];
        }
        delete machines[machineid];
        return [200, true];
    });



};