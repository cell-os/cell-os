# Development (Hacking)

## Writing Service specific gateway endpoints

By default, Gateway service-specific endpoints (`http://X.gw.metal-cell.adobe.io`) forward traffic to any ports configured in the `lb:ports` Marathon label

To customize this behavior, we can:

* Create a new Lua module, `service.APP` which exposes 2 functions: 
* `exec_default` - handler for `http://X.gw.metal-cell.adobe.io/...`
    * For example, for HBase Master this always goes to the active master, instead of doing round-robin between active and backup masters
* `exec_config` - handler for `http://X.gw.metal-cell.adobe.io/config`
    * i.e. for Kafka we go to the scheduler, and then make a call to get the list of brokers which we then send out as a JSON service

## Hacking cell-os base provisioning

If you're modifying or writing a new module, it's much faster (and cheaper) to test your 
changes on an existing cell, than to provision a new cell. 

The relevant part in CLI is the 
[`run_create` method](https://git.corp.adobe.com/metal-cell/cell-os/blob/master/cell.py#L580)
which creates the resources (bucket, cf stack, key) and copies the deployment modules inside
the S3 bucket (`seed` method).

When the machine boots up it will execute `/var/lib/cloud/instance/scripts/part-001` which is 
generated from the `UserData` script 
([source](https://git.corp.adobe.com/metal-cell/cell-os/blob/master/deploy/aws/elastic-cell-scaling-group.py))

The relevant parts in part-001 are:

* provisions `cfn-init` dependencies:
* executes `cfn-init` 
* downloads, unpacks and runs cell modules

    cfn-init -s c1-MembraneStack-Q4TR7ORCOQ9P -r BodyLaunchConfig  --region us-west-1

This will trigger a refresh of all the resources from `InitConfig`.

Note that you can update the cell metadata (CF stack update) along with the cell modules:

    ./cell update $cell_name
    
Then, you can re-run the whole `part-001` script or just the parts that you care about:

> **NOTE:**
You need to source `cellos.sh` in order to get all env variables.  
You need to run as root and `export PATH=$PATH:/usr/local/bin`  
    
    export PATH=$PATH:/usr/local/bin
    source /etc/profile.d/cellos.sh

Downloading cell modules (seed):

    aws s3 cp s3://$cell_bucket_name/${full_cell_name}/shared/cell-os/seed.tar.gz /opt/cell

Once the seeds are retrieved, they are unpacked (`/opt/cell/seed/*`) and then run in two 
stages (for each seed) based on the seed priority (based on seed name e.g. `00-docker`)  

1. `<seed>/provision` (stage 1)
2. `zk-barrier`
3. `<seed>/provision_post` (stage 2)

The `zk-barrier` utility will block until it can find a fully functional Zookeeper 
ensemble reported by Exhibitor endpoint (accessed through ELB).  

> **NOTE:** The only requirement is that the `provision` scripts are executable
Make sure that they have the right [sha-bang](http://www.tldp.org/LDP/abs/html/sha-bang.html)
E.g. `#!/bin/bash`

## Running Gateway tests

Adobe.io gateway integration has a series of integrated tests that you can run. 
To run them, you need a Docker setup. 

To run the tests pass in the `MOUNT` variable the location where the cell-os checkout is mounted on the Docker machine. For example, if you have Docker running in a VM and the cell-os directory is mounted at /cell, pass `MOUNT=/cell`
 
```
cd deploy/seed/99-cell/apigateway
MOUNT=/RemoteHome make test
```

# Releasing

## Builds and Artifacts 

All cell-os builds are available in 
[Jenkins](http://bucasit-build.corp.adobe.com:8080/jenkins/view/cell-os/)

* cell-os
  * cell-os version bundle(s)
  * cli
  * CloudFormation templates
* cell-universe
  * contains cell-os packages
* puppet-X
* docker-X

Puppet modules (used in seeds) and docker containers are released independently and
referenced in version bundles

## cell-universe
The CellOS DCOS repository 
[cell-universe](https://git.corp.adobe.com/metal-cell/cell-universe) is
released separately.

> **NOTE:**  
The repository version needs to have exactly 3 version components 
(e.g. `1.3.0`)  
Currently this also needs to match the cell-os release version (see CELL-375)
for a discussion on changing that.


## Release process

CellOS follows the [HSTACK guidelines on release management](https://git.corp.adobe.com/pages/hstack/opendev/hstack_release_mgmt.html)

We don't have a regular cadence yet, but there's typically a convened scope for
every release, so there should be a shared understanding on when that's exepcted.
The designated release engineer should ensure that her actions won't surprise
the maintainers.

1. Send out a heads up email in advance of the actual RC to have maintainers 
think what they'd want in and out.
1. Create next major and optionally minor versions. 
  * If releasing 1.0.0, next major is 1.1.0, optionally next minor is 1.0.1.
1. Discuss remaining issues and move them to next versions.
1. Review and update all documentation (take special care to remove dead sections)
1. Review all issues and commits and create a summary for the release notes.
  * Write an overview of the release, containing major features, changes from 
  the previous version
  * Don't rush this. Take your time and write a good quality piece. Get feedback 
  from maintainers.
1. Lock any versions that need locking (e.g. "SNAPSHOT", "latest", ">=" in requirements.txt.
1. Update version fron SNAPSHOT to RC1 
  * [`VERSION`](https://git.corp.adobe.com/metal-cell/cell-os/blob/master/VERSIO://git.corp.adobe.com/metal-cell/cell-os/blob/master/VERSION)
  * also grep for the development version and verify any documents that have the 
  version hardcoded (e.g. README.md URLs) 
1. Push the release and anounce it in a "[VOTE]" email that contains:
  * links to the released artefacts
  * links to JIRA
  * the actual release notes 
1. If the vote passes, rinse and repeat (the last 2 steps) and release without the RC
suffix


