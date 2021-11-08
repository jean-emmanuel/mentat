.PHONY: all
all:
	python3 build_docs.py > docs.md && pandoc -s --toc --template=template.html docs.md -o index.html --metadata title="Mentat"
