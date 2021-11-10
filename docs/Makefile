.PHONY: all
all:
	python3 module_docs.py > docs.md
	cat head.md docs.md > index.md
	pandoc -s --toc --template=template.html index.md -o index.html --metadata title="Mentat"
	rm -f docs.md index.md
