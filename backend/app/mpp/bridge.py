from __future__ import annotations

_started = False


def ensure_jvm() -> None:
    global _started
    import jpype
    import mpxj  # noqa: F401 - registers MPXJ jars on the JPype classpath

    if not jpype.isJVMStarted():
        jpype.startJVM(convertStrings=False)
        _started = True
    else:
        thread = jpype.java.lang.Thread
        if hasattr(thread, "isAttached") and not thread.isAttached():
            thread.attach()
