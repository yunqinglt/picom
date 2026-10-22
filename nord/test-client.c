/* SPDX-License-Identifier: MIT
 * Small X11 fixture used by test-runtime.py; no input reaches the host session.
 */
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
    Display *d = XOpenDisplay(NULL);
    if (!d) return 2;
    int parent = argc > 1 && !strcmp(argv[1], "parent");
    Window root = DefaultRootWindow(d);
    Window w = XCreateSimpleWindow(d, root, parent ? 5000 : 100, 100,
                                   parent ? 1280 : 480, parent ? 800 : 300,
                                   2, 0xb48ead, 0xa3be8c);
    if (parent) {
        XSetWindowAttributes attrs = {.override_redirect = True};
        XChangeWindowAttributes(d, w, CWOverrideRedirect, &attrs);
    }
    XClassHint cls = {.res_name = "nord-test", .res_class = "NordTest"};
    XSetClassHint(d, w, &cls);
    XStoreName(d, w, argc > 1 ? argv[1] : "nord-test");
    Atom close = XInternAtom(d, "WM_DELETE_WINDOW", False);
    XSetWMProtocols(d, w, &close, 1);
    XSelectInput(d, w, ExposureMask | StructureNotifyMask);
    XMapWindow(d, w);
    XFlush(d);
    printf("0x%lx\n", w);
    fflush(stdout);
    for (;;) {
        XEvent event;
        XNextEvent(d, &event);
        if (event.type == ClientMessage && event.xclient.data.l[0] == (long)close)
            break;
    }
    XDestroyWindow(d, w);
    XCloseDisplay(d);
    return 0;
}
