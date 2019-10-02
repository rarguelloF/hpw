publish:
	@echo $(TAG)Publishing package to pypi$(END)
	python setup.py sdist upload -r pypi
.PHONY: publish
