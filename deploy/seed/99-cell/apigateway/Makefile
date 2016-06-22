BUILD_DIR ?= target
MOUNT ?= ${HOME}

.PHONY: test

test:
	echo "running tests with docker ..."
	mkdir  -p $(BUILD_DIR)
	mkdir  -p $(BUILD_DIR)/test-logs
	mkdir -p ${MOUNT}/tmp/apiplatform/api-gateway-config
	#cp -r test/resources/api-gateway $(BUILD_DIR)
	#sed -i '' 's/127\.0\.0\.1/redis\.docker/g' $(BUILD_DIR)/api-gateway/redis-upstream.conf
	rm -f $(BUILD_DIR)/test-logs/*
	mkdir -p ${MOUNT}/tmp/apiplatform/api-gateway-config
	cp -r ./api-gateway-config/* ${MOUNT}/tmp/apiplatform/api-gateway-config/
	cp -r ./target ${MOUNT}/tmp/apiplatform/api-gateway-config/
	echo " ... generating resolvers.conf"
	echo resolver $$(awk 'BEGIN{ORS=" "} /nameserver/{print $$2}' /etc/resolv.conf | sed "s/ $$/;/g") > ${MOUNT}/tmp/apiplatform/api-gateway-config/conf.d/includes/resolvers.conf
	- docker run --rm -e "DEBUG=true" \
					-e  "TEST_NGINX_PORT=1981" \
					-v ${MOUNT}/tmp/apiplatform/api-gateway-config:/etc/api-gateway \
					-v ${MOUNT}/tmp/apiplatform/api-gateway-config/target/:/t \
					--entrypoint prove \
				 adobeapiplatform/apigateway:1.1.0 -I /usr/local/test-nginx-0.24/lib -I /usr/local/test-nginx-0.24/inc -r /etc/api-gateway/tests

	cp -r ${MOUNT}/tmp/apiplatform/api-gateway-config/target/* ./target/
	rm -rf ${MOUNT}/tmp/apiplatform/api-gateway-config