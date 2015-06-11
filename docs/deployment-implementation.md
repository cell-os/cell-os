
The `cell-os-base` components are installed directly on the OS while the rest of the cell-os 
components are installed using the cluster-level schedulers (e.g. Marathon) running on top of Mesos.

The steps involved are:

* infrastructure provisioning
* OS bootstrapping (saasbase_installer, puppet)
* cell-os-base (cell-os-base version bundle, installation)
* cell-os


Infrastructure provisioning
--------------------------

### AWS
Currently only AWS infrastructure is automated using CloudFormation.
The os level bootstrapping and cell-os-base are also handled by CloudFormation.

### Bare-metal 
For bare-metal clusters you need to provision the OS yourself and then define a saasbase-deployment
cluster manifest.  
You can use [these as templates](https://git.corp.adobe.com/metal-cell/clusters/)
TODO: 
- [ ] - create a template or utility 

os, bootstrapping
----------------

[saasbase-deployment](https://git.corp.adobe.com/saasbase/saasbase-deployment) `saasbase_installer` 
is used for bootstrapping the host OS.

This can be downloaded from the public saasbase-repo in S3, but in order for it to fetch the rest
of the packages from S3 the saasbase-repo AWS access/secret keys need to be set.
Read more in the [saasbase-deployment documentation](https://git.corp.adobe.com/saasbase/saasbase-deployment/blob/gh-pages/operations/deployment.md#deploy-saasbase-on-all-machines-in-cluster-deploy)



cell-os-base
------------
### version bundle

A version bundle is a file that contains all packages and versions used in a particular release.

`cell-os-base-1.0-SNAPSHOT.yaml`

For example
```
docker::version: 1.6.2
zookeeper::version: 3.4.6_1.5.4
...

modules:
  puppet-zookeeper: 0.1.0-adobe-SNAPSHOT
  ...
  puppet-marathon: 0.1.2-adobe-SNAPSHOT
```

The root elements specify the version for each component.
The `modules:` specify the versions of the installation modules being used.

`saasbase-deployment` will first download / "install" the puppet modules and then install the
actual packages using these modules. 


Docker is installed directly from a package (e.g. `tar.gz`).
The rest of the components come packaged as Docker containers.

* puppet: docker
* puppet: zookeeper docker-based systemd unit
* puppet: mesos docker-based systemd unit
* puppet: marathon docker-based systemd unit

cell-os
-------

The rest of the cell-os services are deployed using one of the cluster-level schedulers (e.g. Marathon)

marathon: chronos docker



