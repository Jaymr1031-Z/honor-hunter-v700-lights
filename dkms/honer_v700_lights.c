// SPDX-License-Identifier: GPL-2.0
#include <linux/acpi.h>
#include <linux/dmi.h>
#include <linux/hex.h>
#include <linux/kobject.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/slab.h>
#include <linux/sysfs.h>

#define LIGHT_GUID "ABBC0F5B-8EA1-11D1-A000-C90629100000"
static DEFINE_MUTEX(light_lock);
static struct kobject *light_kobj;
static u8 response[256];

static bool valid_request(const u8 *p)
{
	unsigned int limit, i;
	if (p[0] != 6 || (p[1] != 5 && p[1] != 6))
		return false;
	if (p[2] != 0xa0 && p[2] != 0xb0 && p[2] != 0xd0)
		return false;
	limit = p[2] == 0xa0 ? 9 : (p[2] == 0xb0 ? 17 : 69);
	if (p[1] == 6) {
		if (p[3] > limit)
			return false;
		for (i = 4; i < 64; i++)
			if (p[i])
				return false;
	} else {
		if (p[3] > 7 || p[4] > p[5] || p[5] > limit ||
		    !p[8] || p[8] > 16)
			return false;
		for (i = 9 + 3 * p[8]; i < 64; i++)
			if (p[i])
				return false;
	}
	return true;
}

static int execute_request(u8 *p)
{
	struct acpi_buffer in = {64, p};
	unsigned int attempt;
	int err = -EIO;
	for (attempt = 0; attempt < 2; attempt++) {
		struct acpi_buffer out = {ACPI_ALLOCATE_BUFFER, NULL};
		union acpi_object *obj, *buf;
		acpi_status status;
		status = wmi_evaluate_method(LIGHT_GUID, 0, 1, &in, &out);
		obj = out.pointer;
		if (ACPI_FAILURE(status) || !obj) {
			kfree(out.pointer);
			return -ENODEV;
		}
		buf = obj;
		if (obj->type == ACPI_TYPE_PACKAGE && obj->package.count == 2)
			buf = &obj->package.elements[1];
		if (buf->type == ACPI_TYPE_BUFFER && buf->buffer.length == 256)
			memcpy(response, buf->buffer.pointer, sizeof(response));
		else if (buf->type == ACPI_TYPE_BUFFER && buf->buffer.length == 260)
			memcpy(response, buf->buffer.pointer + 4, sizeof(response));
		else {
			kfree(out.pointer);
			return -EPROTO;
		}
		err = response[0] ? -EIO : 0;
		kfree(out.pointer);
		if (!err)
			break;
	}
	return err;
}

static ssize_t request_store(struct kobject *kobj,
		struct kobj_attribute *attr, const char *buf, size_t count)
{
	char *copy, *hex;
	u8 request[64];
	int err;
	if (count < 128 || count > 129)
		return -EINVAL;
	copy = kstrndup(buf, count, GFP_KERNEL);
	if (!copy)
		return -ENOMEM;
	hex = strim(copy);
	err = strlen(hex) == 128 ? hex2bin(request, hex, 64) : -EINVAL;
	kfree(copy);
	if (err || !valid_request(request))
		return -EINVAL;
	mutex_lock(&light_lock);
	err = execute_request(request);
	mutex_unlock(&light_lock);
	return err ? err : count;
}

static ssize_t response_show(struct kobject *kobj,
		struct kobj_attribute *attr, char *buf)
{
	unsigned int i;
	ssize_t n = 0;
	mutex_lock(&light_lock);
	for (i = 0; i < sizeof(response); i++)
		n += sysfs_emit_at(buf, n, "%02x", response[i]);
	n += sysfs_emit_at(buf, n, "\n");
	mutex_unlock(&light_lock);
	return n;
}

static struct kobj_attribute request_attr = __ATTR_WO(request);
static struct kobj_attribute response_attr = __ATTR_RO(response);
static struct attribute *light_attrs[] = {
	&request_attr.attr, &response_attr.attr, NULL
};
static const struct attribute_group light_group = {.attrs = light_attrs};

static int __init lights_init(void)
{
	int err;
	if (!dmi_match(DMI_SYS_VENDOR, "HUAWEI") ||
	    !dmi_match(DMI_PRODUCT_NAME, "FRD-WX9") || !wmi_has_guid(LIGHT_GUID))
		return -ENODEV;
	request_attr.attr.mode = 0200;
	response_attr.attr.mode = 0400;
	light_kobj = kobject_create_and_add("honer_v700_lights", kernel_kobj);
	if (!light_kobj)
		return -ENOMEM;
	err = sysfs_create_group(light_kobj, &light_group);
	if (err)
		kobject_put(light_kobj);
	return err;
}

static void __exit lights_exit(void)
{
	sysfs_remove_group(light_kobj, &light_group);
	kobject_put(light_kobj);
}

module_init(lights_init);
module_exit(lights_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("FRD-WX9 RGB WMI bridge (LOGO, 4-zone Keyboard, 70-LED Wind Valley)");
