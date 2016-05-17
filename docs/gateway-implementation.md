# Intro

The Adobe.io gateway is an NGINX server with a series of addons for load balancing, service discovery, etc.

The docker image we use comes preconfigured to enable HDFS, Mesos, Marathon and Zookeeper(Exhibitor) access out of the box (through simple env configuration).

In addition the gateway syncs it's entire configuration from a remote source (currently S3 set through `REMOTE_CONFIG` env var).

Gateway provisioning

https://git.corp.adobe.com/metal-cell/cell-os/blob/master/deploy/seed/99-cell/provision_post


To manually start a gw container:
```
docker run \
-e "MARATHON_HOST=http://ip-10-27-15-200.ut1.adobe.net:8080" \
-e "MESOS_MASTER_HOST=http://ip-10-27-15-203.ut1.adobe.net:5050" \
-e "HDFS_NN1_HOST=ip-10-27-15-201.ut1.adobe.net" \
-e "HDFS_NN2_HOST=ip-10-27-15-201.ut1.adobe.net" \
-e "REMOTE_CONFIG=s3://cell-os--c4/cell-os--c4/membrane/apigateway/api-gateway-config" \
-e "LOG_LEVEL=debug" \
-e "AWS_ACCESS_KEY_ID=xxxxxxxxxxxxxxxxxxxxxx" \
-e "AWS_SECRET_ACCESS_KEY=yyyyyyyyyyyyyyyyyy" \
--net=host \
cellos/apigateway:1.9.7.3
```

To attach to an existing gateway:

SSH into one membrane node

    ./cell ssh <cell> membrane 1


Attach to gateway

    docker ps # to get the gw container id
    docker exec -it <container> bash

Inside the container

* `/etc/api-gateway` - this is where the gw configuration is synced from `REMOTE_CONFIG` path
* `/var/log/api-gateway/*` - gateway logs

Reload

    api-gateway -s reload

# Marathon generated 
`/etc/apigateway/environment.conf.d/api-gateway-upstreams.http.conf`

