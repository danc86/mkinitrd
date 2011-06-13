#!/usr/bin/env python

import os
import sys
import tempfile
import shutil
import re
import subprocess
from glob import glob

def check_output(*args, **kwargs):
    p = subprocess.Popen(*args, stdout=subprocess.PIPE, **kwargs)
    out = p.communicate()[0]
    if p.returncode != 0:
        raise RuntimeError('Command %r exited with return code %r'
                % (args[0], p.returncode))
    return out

install_set = dict()

class Dir(object):
    def install_to(self, dest):
        os.mkdir(dest)

class File(object):
    def __init__(self, path):
        self.path = path
    def install_to(self, dest):
        shutil.copy2(self.path, dest)

class Symlink(object):
    def __init__(self, target):
        self.target = target
    def install_to(self, dest):
        os.symlink(self.target, dest)

def install_dir(path):
    install_set[path] = Dir()

def install_config(path):
    install_set[path] = File(path)

def install_binary(path):
    install_set[path] = File(path)
    for line in check_output(['ldd', path]).splitlines():
        if re.match(r'\s*linux-vdso\.so', line):
            continue
        m = re.match(r'\s*(\S+) => (\S+)\s+\(0x', line)
        if m:
            lib = m.group(2)
        else:
            m = re.match(r'\s*(\S+)\s+\(0x', line)
            lib = m.group(1)
        install_set[os.path.realpath(lib)] = File(lib)
        if os.path.islink(lib):
            install_set[os.path.join(os.path.realpath(os.path.dirname(lib)), os.path.basename(lib))] \
                = Symlink(os.readlink(lib))

def install_symlink(path, target):
    install_set[path] = Symlink(target)

def install_tree(path):
    for dirpath, dirnames, filenames in os.walk(path):
        install_set[dirpath] = Dir()
        for filename in filenames:
            path = os.path.join(dirpath, filename)
            install_set[path] = File(path)

def main():
    install_dir('/newroot')
    install_dir('/sys')
    install_dir('/proc')
    install_dir('/dev')
    install_dir('/run')
    install_symlink('/lib', 'lib64')
    install_binary('/bin/bash')
    install_binary('/sbin/udevd')
    install_binary('/sbin/udevadm')
    install_config('/etc/mdadm.conf')
    install_binary('/sbin/mdadm')
    for binary in glob('/sbin/fsck*'):
        install_binary(binary)
    install_binary('/sbin/dmsetup')
    install_binary('/sbin/blkid')
    install_binary('/sbin/lvm')
    for program in ['lvchange', 'lvconvert', 'lvcreate', 'lvdisplay', 
            'lvextend', 'lvmchange', 'lvmdiskscan', 'lvmsadc', 'lvmsar', 'lvreduce', 
            'lvremove', 'lvrename', 'lvresize', 'lvs', 'lvscan', 'pvchange', 'pvck', 
            'pvcreate', 'pvdisplay', 'pvmove', 'pvremove', 'pvresize', 'pvs', 'pvscan', 
            'vgcfgbackup', 'vgcfgrestore', 'vgchange', 'vgck', 'vgconvert', 'vgcreate', 
            'vgdisplay', 'vgexport', 'vgextend', 'vgimport', 'vgmerge', 'vgmknodes', 
            'vgreduce', 'vgremove', 'vgrename', 'vgs', 'vgscan', 'vgsplit']:
        install_symlink('/sbin/%s' % program, 'lvm')
    install_binary('/usr/bin/cat')
    install_binary('/usr/bin/ls')
    install_binary('/usr/bin/ln')
    install_binary('/usr/bin/ed')
    install_binary('/usr/bin/less')
    install_binary('/usr/bin/mkdir')
    install_binary('/bin/pidof')
    install_binary('/bin/mount')
    install_binary('/bin/umount')
    install_binary('/sbin/switch_root')
    install_tree('/lib64/udev')
    install_tree('/etc/udev')

    tmpdir = tempfile.mkdtemp(prefix='mkinitrd')
    print 'Building initrd in %s ...' % tmpdir
    for path, obj in sorted(install_set.items(),
            key=lambda (path, obj): (isinstance(obj, Symlink), path)):
        print path
        dest = tmpdir + path
        if not os.path.exists(os.path.dirname(dest)):
            os.makedirs(os.path.dirname(dest))
        obj.install_to(dest)
    open(tmpdir + '/init', 'w').write('''#!/bin/bash

export PATH=/sbin:/usr/bin:/bin
export EDITOR=ed

function edo() {
    [ -e /dev/kmsg ] && echo "initrd: $*" >/dev/kmsg
    $* 2>&1 >/dev/kmsg || ( echo "Bailing..." ; exec /bin/bash )
}

# mount important stuff
edo mount -n -t devtmpfs -o mode=0755 udev /dev
edo mkdir /dev/shm /dev/pts 
edo mkdir -p -m 0755 /dev/.udev/rules.d
edo mount -n -t devpts -o gid=5,mode=620 devpts /dev/pts
edo mount -n -t tmpfs tmpfs /dev/shm
edo mount -n -t sysfs none /sys
edo mount -n -t proc none /proc
cmdline=$(cat /proc/cmdline)
edo mount -n -t tmpfs tmpfs /run

# let udev do its thing
edo udevd --daemon --resolve-names=never
edo udevadm settle

# set up some nice block devices to mount
edo mdadm --quiet --assemble --scan
edo vgchange -a y

# pass fixme in kernel args to get a shell for fixing things
for arg in $cmdline ; do
    if [[ "$arg" == fixme ]] ; then
        ( export PS1='fixme$ ' ; bash )
        break
    fi
done

# the important bit: mount root, and /usr if defined
root_mounted=""
for arg in $cmdline ; do
    if [[ "$arg" == root=* ]] ; then
        edo fsck -a "${arg:5}"
        edo mount -n -r "${arg:5}" /newroot
        root_mounted="true"
        break
    fi
done
edo [ $root_mounted ]
( while read -r dev mountpoint type opts rest ; do
    if [[ "$dev" != \#* ]] && [[ "$mountpoint" == /usr ]] ; then
        edo fsck -a "$dev"
        edo mount -n -r -t "$type" -o "$opts" "$dev" /newroot/usr
        break
    fi
done ) </newroot/etc/fstab 

# clean up
edo udevadm control --exit
edo umount -n /dev/pts
edo umount -n /dev/shm
edo mount --move /run /newroot/run

# sanity check
edo [ -x /newroot/sbin/init ]

# switch to the new root
edo exec switch_root /newroot /sbin/init $cmdline
''')
    os.chmod(tmpdir + '/init', 0755)

    image = '/boot/initramfs.img'
    print 'Writing image to %s' % image
    subprocess.check_call('find . | cpio --quiet -o -H newc | gzip -9',
            stdout=open(image, 'w'), shell=True, cwd=tmpdir)

    shutil.rmtree(tmpdir)

if __name__ == '__main__':
    main()
