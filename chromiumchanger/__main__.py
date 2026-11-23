import argparse

from . import settings


def main():
    ap = argparse.ArgumentParser(prog="chromiumchanger")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("gui", help="open the desktop app (default)")
    sub.add_parser("install", help="download/install ungoogled-chromium")
    sub.add_parser("apply", help="apply settings to extension/policies/branding")
    sub.add_parser("launch", help="apply settings, then launch the browser")
    sub.add_parser("uninstall-policies", help="remove registry policies")
    sub.add_parser("remove-browser", help="remove the customized browser, its data, policies and shortcuts (asks first)")
    a = ap.parse_args()
    if a.cmd in (None, "gui"):
        from . import gui
        gui.main()
        return
    settings.init()
    from . import fetcher, launcher, policies
    if a.cmd == "install":
        fetcher.install()
    elif a.cmd == "apply":
        launcher.build_all()
    elif a.cmd == "launch":
        launcher.launch()
    elif a.cmd == "uninstall-policies":
        policies.remove()
    elif a.cmd == "remove-browser":
        from . import cleanup
        print("This will remove:\n  - " + "\n  - ".join(cleanup.describe()))
        if input("Type YES to continue: ").strip() == "YES":
            cleanup.run()


if __name__ == "__main__":
    main()
