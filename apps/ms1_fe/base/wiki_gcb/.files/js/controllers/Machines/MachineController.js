
angular.module('cloudscalers.controllers')
    .controller('MachineController', ['$scope', 'Machine', 'Size', 'Image', '$ErrorResponseAlert', '$location', '$alert', '$rootScope',
      function($scope, Machine, Size, Image, $ErrorResponseAlert, $location, $alert, $rootScope) {

        $scope.$watch('currentspace.accountId',function(){
            if ($scope.currentSpace){
                $scope.images = Image.list($scope.currentSpace.accountId, $scope.currentSpace.id);
            }
        });

        $scope.updateMachineList = function(){
            var cloudspaceId;
            $scope.machines = {};
            $scope.machinesLoader = true;

            if($location.search().cloudspaceId){
              cloudspaceId = parseInt($location.search().cloudspaceId);
              $scope.$watch('cloudspaces',function(){
                if($scope.cloudspaces){
                  var navigatedSpace = _.findWhere($scope.cloudspaces, {id: parseInt($location.search().cloudspaceId)});
                  if(navigatedSpace){
                    $scope.setCurrentCloudspace(navigatedSpace);
                    callMachinesListApi(cloudspaceId);
                  }else{
                    $alert("You don't have access to this CloudSpace.");
                    delete $location.search().cloudspaceId;
                    $scope.setCurrentCloudspace($scope.cloudspaces[0]);
                    callMachinesListApi($scope.currentSpace.id);
                    $location.path('/');
                  }
                }
              });
            }else{
              if($scope.currentSpace){
                callMachinesListApi($scope.currentSpace.id);
              }
            }

            function callMachinesListApi(cloudspaceId) {
              Machine.list(cloudspaceId).then(
                  function(machines){
                    $scope.machines = machines;
                    $scope.machinesLoader = false;
                  },
                  function(reason){
                      $scope.machinesLoader = false;
                      $ErrorResponseAlert(reason);
                  }
              );
            }
        }

        $scope.updateMachineName = function(machineId){
          console.log($scope.machines);
          for (var i = 0; i < $scope.machines.length; i++) {
            console.log($scope.machines[i])
          }
        }

        $scope.$watch('currentSpace.id',function(){
          if($scope.currentSpace){
            $scope.updateMachineList();
            Size.list($scope.currentSpace.id).then(function(sizes){
              $scope.sizes = sizes;
            },function(reason){
              $ErrorResponseAlert(reason);
            });
          }
        });

        $rootScope.$on('callUpdateMachineList', function(event, args) {
          $scope.updateMachineList();
        });

        $scope.machineIsManageable = function(machine){
            return machine.status && machine.status != 'DESTROYED' && machine.status != 'ERROR';
        }

        $scope.packageDisks = "";


        $scope.machineinfo = {};
        $scope.numeral = numeral;

        var updateMachineSizes = function(){
            $scope.machineinfo = {};
            _.each($scope.machines, function(element, index, list){
                $scope.machineinfo[element.id] = {};
                size = _.findWhere($scope.sizes, { id: element.sizeId });
                $scope.machineinfo[element.id]['size'] = size;
                image = _.findWhere($scope.images, { id: element.imageId });
                $scope.machineinfo[element.id]['image'] = image;
                $scope.machineinfo[element.id]['storage'] = element.storage;
                }
            )

        };

        $scope.$watch('machines', updateMachineSizes);
        $scope.$watch('sizes', updateMachineSizes, true);
        $scope.$watch('images', updateMachineSizes, true);

    }
]);
