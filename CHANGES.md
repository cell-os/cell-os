## Release 1.2-rc1 - 2016-03-03

### Summary

* Service and Configuration Discovery
* Load Balancing
* New core services: Kafka, HBase, OpenTSDB
* New CellOS Services Repository 
* DCOS Universe support and dcos-cli integration
* New CLI (rewritten in Python)
* Provisioning status page
* Package upgrades: java-8u74, docker-1.10.2, mesos-0.27.1, marathon-v0.15.3
* Default AMI upgrades (kernel, enhanced networking, larger root, etc.)
* OS networking performance tuning
* Revamped documentation

### Improvement

    * [CELL-51] - Assign different instance types based on the role assigned to an instance
    * [CELL-67] - ./cell improved keypair support
    * [CELL-80] - [DOC] - Recommended Docker base images
    * [CELL-81] - cell-os gateway service
    * [CELL-83] - Kafka Cell package
    * [CELL-132] - Increase permissions for all node roles
    * [CELL-133] - Decouple cell-os-base installation mechanism from AWS specific features (CFN)
    * [CELL-139] - Get rid of troposphere_helpers.py (move to tropopause library)
    * [CELL-140] - Add created load balancers as CloudFormation outputs
    * [CELL-148] - Remove redundant defaults from substack
    * [CELL-150] - ./cell list should list the s3 bucket
    * [CELL-151] - Set cell role / subdivision as mesos slave attribute
    * [CELL-154] - Ability to pass in instance type for different cell roles
    * [CELL-155] - Add get_ip script to cell instances
    * [CELL-156] - Use ./cell as a frontend for Zookeeper (Exhibitor), Mesos, Marathon
    * [CELL-157] - Mesos configuration should use ip_discovery_command
    * [CELL-158] - Mesos slave configuration updates: consistent tmp directory, gc for containers
    * [CELL-159] - Upgrade to Docker 1.9
    * [CELL-161] - Rewrite ./cell in Python
    * [CELL-164] - ./cell "list" command should show only cells not all stacks
    * [CELL-165] - zk_barrier should output some progress
    * [CELL-166] - Yum failures with upstream docker repo
    * [CELL-167] - Create SSH key on cell creation instead of reusing existing key
    * [CELL-168] - ./cell should rollback previously created resources, on failure
    * [CELL-169] - elbs should be available profile.d/cellos.sh
    * [CELL-170] - Public access to membrane ELB
    * [CELL-171] - auto launch gateway on cell creation
    * [CELL-172] - ./cell externally provided bucket configuration
    * [CELL-176] - random repos.mesosphere.io host not found
    * [CELL-179] - Enable all protocols within the cell bodies (not only TCP)
    * [CELL-184] - Mount Exhibitor zk data dir as an external volume
    * [CELL-185] - ./cell auto validate dependencies, check for updates
    * [CELL-186] - DNS - A Record Alias support
    * [CELL-187] - Mangle Mesos UI URLs to work with the gateway
    * [CELL-191] - Seed provision bash issue [: ==: unary operator expected
    * [CELL-193] - remove redundant piece ("-lb-") from elb name
    * [CELL-194] - Cell status page
    * [CELL-199] - Mesos /master/redirect should redirect to the Gateway
    * [CELL-200] - ./cell.py - proxy weird issues with backgrounding from a Python app
    * [CELL-204] - ./cell.py - add ssh timeout option
    * [CELL-208] - ./cell.py - print tables using awscli table formatter
    * [CELL-209] - ./cell.py - check if keyfile exists before attempting to delete
    * [CELL-210] - Open HTTP access to the "shared/http" folder
    * [CELL-212] - puppet-zookeeper: rename container to zookeeper
    * [CELL-214] - Lock pip version to <8
    * [CELL-215] - Lock aws-cli version
    * [CELL-216] - Explicitly state dependency on InternetGateway to avoid race condition
    * [CELL-218] - gateway provision retry logic
    * [CELL-225] - swap cell.py -> cell, cell -> cell.sh
    * [CELL-226] - [DOC] - service discovery / load balancing
    * [CELL-229] - Marathon - stderr and stdout should be downloaded through the Gateway
    * [CELL-230] - Mesos / Kafka Mesos interaction with --switch_user flag in Mesos
    * [CELL-231] - DCOS Packages support
    * [CELL-233] - Gateway - `master/state.json` API should be routed to Mesos leader
    * [CELL-234] - [DOC] - 1.2 doc revamp
    * [CELL-237] - Create sub-command to connect to the cell via tmux/tmuxinator
    * [CELL-238] - DCOS Kafka package customizations
    * [CELL-239] - HBase Cell package
    * [CELL-240] - DCOS OpenTSDB Cell Package
    * [CELL-241] - Configure default AWS VPC DNS server to workaround resolve issues at boot
    * [CELL-243] - ./cell: replace deprecated os.system calls to hide background command output
    * [CELL-245] - Cache configuration files
    * [CELL-250] - Add CloudWatch logs for cell provisioning
    * [CELL-251] - Upgrade exhibitor-puppet docker image to Exhibitor 1.5.6 and JDK8
    * [CELL-254] - Cell log polling should use native ncurses library instead of external watch command
    * [CELL-258] - Cell package should installable via pip from git
    * [CELL-263] - Update default AMI (latest kernel, enhanced networking)
    * [CELL-266] - ./cell - various small fixes / refactorings
    * [CELL-269] - Cell list command should print out statuspage url
    * [CELL-272] - zk-barrier tracing entry (for status)
    * [CELL-277] - [DOC] - configuration discovery
    * [CELL-280] - Make gateway available from inside the cell
    * [CELL-281] - Dynamic /config lua modules for configuration layers
    * [CELL-285] - Kafka package multi-cluster support
    * [CELL-286] - DCOS - deep-merge package options and user options
    * [CELL-289] - Create generic cell endpoint in DCOS config
    * [CELL-290] - Kafka dynamic config endpoint
    * [CELL-291] - HBase dynamic config endpoint
    * [CELL-296] - Prototype initial base provisioning tracing
    * [CELL-298] - ./cell list fails, if aws env not set, ignoring cell config
    * [CELL-299] - report_status should report to stdout as well
    * [CELL-300] - report_status should capture all arguments
    * [CELL-301] - seed report zk_barrier
    * [CELL-309] - HBase DCOS package customization
    * [CELL-316] - [Gateway] Fix lua globals with local variables
    * [CELL-318] - ./cell operations should fail with a friendly message if cell doesn't exist
    * [CELL-319] - [Gateway] - Define ngx.apiGateway.config to store lua configs
    * [CELL-322] - ./cell dcos package throws an error instead of showing the documentation
    * [CELL-325] - [DOC] - HBase deployment and configuration endpoint
    * [CELL-327] - HBase Gateway microservice loads inexistent module "inspect"
    * [CELL-330] - regression ./cell.py - allocate a tty on ./cell cmd to allow sudo
    * [CELL-335] - [Gateway] - When HDFS NN1 is down, route to NN2
    * [CELL-336] - HBase package does not support LZO compression
    * [CELL-337] - DCOS: hbase-regionserver should start with one instance
    * [CELL-340] - Network performance tuning for cellos nodes
    * [CELL-343] - Freeze pip requirements
    * [CELL-345] - [DOC] - release tasks
    * [CELL-354] - [DOC] - OpenTSDB package
    * [CELL-356] - [BUMP] - docker 1.10.2, java 8u74
    * [CELL-357] - OpenTSDB init should fail if table creation fails
    * [CELL-360] - Configure mesos port range for the body
    * [CELL-361] - Refactor OpenTSDB init
    * [CELL-364] - [DOC] - 1.2 Release Notes
    * [CELL-84] - Workloads should be able to specify specific docker auth
    * [CELL-85] - cell-os public / private registries
    * [CELL-135] - Install the Gateway
    * [CELL-136] - Expose Mesos UI and API through the Gateway
    * [CELL-137] - Expose Exhibitor through the Gateway
    * [CELL-138] - Expose Marathon UI and API through the Gateway
    * [CELL-181] - Expose HDFS namenodes through the gateway
    * [CELL-188] - Restrict cell admin access to Adobe net IPs
    * [CELL-273] - HBase Cell package: gateway module

### Bug

    * [CELL-92] - docker 1.8 takes 5 minutes on first start
    * [CELL-120] - Volumes are not deleted on termination
    * [CELL-134] - Regression: ./cell list shouldn't output substacks
    * [CELL-147] - Configure ingress to all Adobe owned IPs
    * [CELL-149] - Can't access mesos slaves (sandboxes) when proxy to nucleus
    * [CELL-162] - post modules not deployed on membrane
    * [CELL-173] - s3 getObject not enabled for membrane and bodies
    * [CELL-175] - "no such device" error with Docker 1.9
    * [CELL-178] - s3 shared folder shouldn't be in bucket root
    * [CELL-183] - use new (fully qualified cell name) s3 path for gateway provision
    * [CELL-189] - Route53 requires the dualstack HostedZoneId (static)
    * [CELL-192] - Document and validate the maximum cell name length
    * [CELL-195] - ./cell.py - ssh "could not resolve hostname" error
    * [CELL-201] - ./cell.py - create S3 bucket in the same region as the stack
    * [CELL-202] - ./cell.py - resources should be deleted in reverse order
    * [CELL-203] - ./cell.py - aws configs aren't loaded
    * [CELL-205] - ./cell.py - ssh user is not used
    * [CELL-206] - ./cell.py - bucket not removed on cell deletion due to bad response parsing
    * [CELL-207] - ./cell.py - abort creation if keyfile exists already
    * [CELL-213] - aws-cli installation failure due to existing installation of "six" package
    * [CELL-221] - Cell gateways listing is invalid
    * [CELL-223] - Docker 1.10: fix docker deprecation warnings
    * [CELL-224] - ./cell.py - environment variable should take priority to configuration
    * [CELL-232] - Build script should install Python prerequisites
    * [CELL-242] - Restrict all gateway access to admin zone by default
    * [CELL-249] - Fix path to Cell DCOS repository
    * [CELL-252] - Build server script can't sudo, should use virtualenv
    * [CELL-253] - Build server script paths are broken after transition to new cell.py
    * [CELL-267] - ./cell config cache invalidation is incorrect
    * [CELL-268] - Statuspage url is invalid for us-east-1 AWS region
    * [CELL-275] - Config caching mechanism has undesired/unintended consequences
    * [CELL-279] - Don't regenerate dcos.toml configuration
    * [CELL-287] - ./cell.py update is broken
    * [CELL-293] - Adobe egress ips are not in sync
    * [CELL-303] - status page chokes on partial data
    * [CELL-304] - Cell status page chokes on partial data
    * [CELL-306] - ./cell list shows marathon instead of hdfs in gw
    * [CELL-307] - error while running example from packaging doc
    * [CELL-310] - HBase config endpoint - use active master
    * [CELL-313] - kafka config endpoint fails (500) if broker added but not started
    * [CELL-314] - ./cell list shows membrane gateway instead of hdfs
    * [CELL-328] - Detect HBase master w/out regionservers
    * [CELL-342] - ./cell.py scaling down is disabled
    * [CELL-358] - cell-universe repository version is incorrect (1.2-SNAPSHOT)
    * [CELL-366] - Parameters for the ./cell dcos subcommand are not quoted

## Release 1.1-rc1 - 2015-12-08

### Comments

### Improvement
    * [CELL-36] - Upgrade Amoeba to CentOS-7.1
    * [CELL-40] - Move quickstart-1 to amoeba
    * [CELL-45] - Public ELBs to monitor and administer Mesos and other components
    * [CELL-51] - Assign different instance types based on the role assigned to an instance
    * [CELL-60] - Add cell-os-base-1.1-SNAPSHOT bundle 
    * [CELL-61] - Change S3 access from keys to IAM role-based access
    * [CELL-62] - Node index defaults to 0, requires index to always be specified
    * [CELL-63] - Reduce unnecessary security groups membership
    * [CELL-71] - cell-cli - allocate a tty on ./cell cmd to allow sudo 
    * [CELL-72] - cf template - saasbase_installer should fetch specified version of embedded modules instead of latest
    * [CELL-75] - Incorrect CF link in README
    * [CELL-76] - CellOsVersionBundle default should be the same as current version (1.1)
    * [CELL-77] - Cell membrane
    * [CELL-79] - Cell stateful body
    * [CELL-82] - elastic cell-os HDFS support
    * [CELL-86] - Extract CF scaling group logic in reusable (nested) stack 
    * [CELL-89] - install cell-os-base JDK 
    * [CELL-91] - Open nucleus access to load balancers
    * [CELL-93] - pre / post zk-barrier modules 
    * [CELL-94] - Marathon LB should check /status instead of / 
    * [CELL-98] - Set instance timezone to UTC
    * [CELL-99] - Troposphere Port
    * [CELL-100] - Hadoop support
    * [CELL-101] - ./cell support for i2cssh
    * [CELL-102] - Drop raw json CF support
    * [CELL-104] - ./cell refactor to use functions
    * [CELL-105] - ./cell override variables from enviornment
    * [CELL-106] - ./cell get path to cell-os dir
    * [CELL-107] - introduce UserData base map that gets on all stacks 
    * [CELL-108] - Use SaasBase access keys only for puppet run
    * [CELL-109] - ./cell list shouldn't output nested stacks
    * [CELL-116] - ./cell i2cssh to role 
    * [CELL-117] - troposphere build support
    * [CELL-121] - Can't create cells with names larger than 7 characters 
    * [CELL-124] - Membrane IAM for read only s3 access
    * [CELL-125] - [RFC] - cell-os-base deployment packages / modules
    * [CELL-127] - Amoeba should use released artifacts instead of git repos
    * [CELL-131] - Add python requirements.txt to the cell-os project
    * [CELL-141] - Ability to configure instance root device size
    * [CELL-144] - Add Adobe Paris egress IP 
    * [CELL-146] - Amoeba: use Vagrant vm.provision instead of ssh to bootstrap
    * [CELL-65] - Pass the AWS region to cluster.yaml in the CF template 

### Bug
    * [CELL-64] - CellOS only works in us-west-2 due to Exhibitor
    * [CELL-69] - cell-cli list <cell> doesn't set output type
    * [CELL-70] - nucleus config doesn't install cfn-bootstrap
    * [CELL-74] - cell-cli doesn't delete s3 bucket
    * [CELL-90] - disable puppet-marathon JDK install
    * [CELL-96] - AWS_OPTIONS are not passed when describing instances
    * [CELL-103] - Minor issues with HDFS provisioning
    * [CELL-118] - CF launch stack should use released template 
    * [CELL-122] - DNS issues in AWS us-east-1
    * [CELL-128] - ./cell i2cssh to all the roles does not work
    * [CELL-129] - Cell nucleus nodes shouldn't run mesos-agent
    * [CELL-130] - Cell update does not work because of the --tags option

