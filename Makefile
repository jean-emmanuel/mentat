deb-changelog:
	gbp dch

deb:
	dpkg-buildpackage --build=binary --unsigned-changes
