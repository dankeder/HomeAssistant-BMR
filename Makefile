push:
	rsync -aHSvP --exclude '__pycache__/' ${RSYNC_ARGS} custom_components/bmr/ root@intel-02.internal:/mnt/k8s-develcraft-home-assistant/config/custom_components/bmr/

.PHONY: push
