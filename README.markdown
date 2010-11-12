This is my mkinitrd script, to generate an initrd image for booting systems 
which use lvm2 on top of md.

The code is largely inspired by/based upon 
[Dracut](http://fedoraproject.org/wiki/Dracut), a more full-featured initrd 
generation system by the Fedora project.

Features:

* Image contents are built entirely from the live filesystem (including dynamic 
  link dependencies)
* Everything is detected automatically at boot time
    * Root filesystem device is parsed from the standard root= kernel 
      argument
    * mdadm --assemble --scan is used, to scan and assemble arrays as per 
      mdadm.conf (copied from the live filesystem)
    * lvm2's autodetection features are used
* If something goes wrong, you get a bash shell (and an opportunity to fix it): 
  this initrd is not suitable for noobs :-)
