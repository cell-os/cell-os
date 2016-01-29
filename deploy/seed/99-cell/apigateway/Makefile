BUILD_DIR ?= target

.PHONY: test

test:
	echo "running tests with docker ..."
	mkdir  -p $(BUILD_DIR)
	mkdir  -p $(BUILD_DIR)/test-logs
	mkdir -p ~/tmp/apiplatform/api-gateway-config
	#cp -r test/resources/api-gateway $(BUILD_DIR)
	#sed -i '' 's/127\.0\.0\.1/redis\.docker/g' $(BUILD_DIR)/api-gateway/redis-upstream.conf
	rm -f $(BUILD_DIR)/test-logs/*
	mkdir -p ~/tmp/apiplatform/api-gateway-config
	cp -r ./api-gateway-config/* ~/tmp/apiplatform/api-gateway-config/
	cp -r ./target ~/tmp/apiplatform/api-gateway-config/
	echo " ... generating resolvers.conf"
	echo resolver $$(awk 'BEGIN{ORS=" "} /nameserver/{print $$2}' /etc/resolv.conf | sed "s/ $$/;/g") > ~/tmp/apiplatform/api-gateway-config/conf.d/includes/resolvers.conf
	docker run --rm -e "DEBUG=true" \
					-v ${HOME}/tmp/apiplatform/api-gateway-config:/etc/api-gateway \
					-v ${HOME}/tmp/apiplatform/api-gateway-config/target/:/t \
					--entrypoint prove \
				 adobeapiplatform/apigateway:latest -I /usr/local/test-nginx-0.24/lib -I /usr/local/test-nginx-0.24/inc -r /etc/api-gateway/tests

	cp -r ~/tmp/apiplatform/api-gateway-config/target/* ./target/
	rm -rf ~/tmp/apiplatform/api-gateway-config