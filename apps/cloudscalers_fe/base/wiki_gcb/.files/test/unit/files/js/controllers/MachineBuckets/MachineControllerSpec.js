describe("Machine bucket controller tests", function(){
	var scope, ctrl, machine;
	var machinelist = [
		{status: "RUNNING", hostname: "jenkins.cloudscalers.com", "description": "JS Webserver", "name": "CloudScalers Jenkins", "nics": [], "sizeId": 0, "imageId": 0, "id": 0},
		{status: "HALTED", hostname: "cloudbroker.cloudscalers.com", "description": "CloudScalers CloudBroker",  "name": "CloudBroker", "nics": [], "sizeId": 0, "imageId": 1, "id": 1}];

	beforeEach(module('cloudscalers'));
	
	beforeEach(inject(function($rootScope) {
		machine = {list : jasmine.createSpy('list'), create: jasmine.createSpy('create'), get: jasmine.createSpy('get') };
		scope = $rootScope.$new();
	}));

	
	describe("machine list", function() {
		beforeEach(inject(function($controller) {
			machine.list.andReturn(machinelist);
		 	ctrl = $controller('MachineController', {$scope : scope, Machine : machine});
		}));

	 	it("provides a list of machines on the service", function() {
			expect(scope.machines.length).toBe(2);
			expect(scope.machines[0].hostname).toBe("jenkins.cloudscalers.com");
			expect(scope.machines[1].hostname).toBe("cloudbroker.cloudscalers.com");
		});
	});

});
