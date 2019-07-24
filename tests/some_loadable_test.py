# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

class TaskClass(object):
    def my_task(self):
        return "I'm a task class method!"

_instantiated_class = TaskClass()

task_class_target = _instantiated_class.my_task

class EmbeddedCallClass(object):
    def __call__(self):
        return "I'm a __call__ method in a class!"

embedded_task_target = EmbeddedCallClass()

def task_method():
    return "I'm a task method!"
