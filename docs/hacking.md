# Writing Service specific gateway endpoints

By default, Gateway service-specific endpoints (`http://X.gw.metal-cell.adobe.io`) forward traffic to any ports configured in the `lb:ports` Marathon label

To customize this behavior, we can:

* Create a new Lua module, `service.APP` which exposes 2 functions: 
* `exec_default` - handler for `http://X.gw.metal-cell.adobe.io/...`
    * For example, for HBase Master this always goes to the active master, instead of doing round-robin between active and backup masters
* `exec_config` - handler for `http://X.gw.metal-cell.adobe.io/config`
    * i.e. for Kafka we go to the scheduler, and then make a call to get the list of brokers which we then send out as a JSON service
