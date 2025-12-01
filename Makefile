FUNCTION_NAME ?= telegram-transcriber-bot
AWS_PROFILE   ?= personal
ZIP_FILE      ?= function.zip
PACKAGE_DIR   ?= package

.PHONY: all package deploy clean

all: package

package: clean
	# Export dependencies from uv.lock to a requirements file
	uv export --format=requirements-txt > locked-requirements.txt

	mkdir -p $(PACKAGE_DIR)
	# Install locked dependencies into package/
	uv pip install --requirement locked-requirements.txt --target $(PACKAGE_DIR)

	# Add lambda code
	cp lambda_function.py $(PACKAGE_DIR)/

	# Zip it
	cd $(PACKAGE_DIR) && zip -r ../$(ZIP_FILE) .

deploy: package
	aws lambda update-function-code \
		--function-name $(FUNCTION_NAME) \
		--zip-file fileb://$(ZIP_FILE) \
		--profile $(AWS_PROFILE)

clean:
	rm -rf $(PACKAGE_DIR) $(ZIP_FILE) locked-requirements.txt
