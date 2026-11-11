"""Drive native callable pages while retaining AppTest's client-side route.

The installed AppTest stores `_page_hash` for file-based switch_page(), but
does not update it after the app calls st.switch_page(callable_page). A real
browser sends the selected hash on subsequent widget reruns. This test-only
subclass carries that already-rendered route forward without changing the app.
"""
from streamlit.testing.v1 import AppTest as StreamlitAppTest


class NativeAppTest(StreamlitAppTest):
    @classmethod
    def from_file(cls, script_path, *, default_timeout=3):
        prepared = StreamlitAppTest.from_file(script_path, default_timeout=default_timeout)
        return cls(prepared._script_path, default_timeout=default_timeout)

    @classmethod
    def _from_string(cls, script, *, default_timeout=3, args=None, kwargs=None):
        # The installed implementation hardcodes the base AppTest constructor
        # here and in from_file, so both factories adopt this subclass.
        prepared = StreamlitAppTest._from_string(script, default_timeout=default_timeout, args=args, kwargs=kwargs)
        return cls(prepared._script_path, default_timeout=default_timeout, args=args, kwargs=kwargs)

    def _run(self, *args, **kwargs):
        result = super()._run(*args, **kwargs)
        if not self.exception and "_native_routes" in self.session_state and "explore_page" in self.session_state:
            routes = self.session_state["_native_routes"]
            current = self.session_state["explore_page"]
            if current in routes:
                self._page_hash = routes[current]._script_hash
        return result


def open_page(app, page):
    app.session_state["_requested_page"] = page
    app.run()
    assert not app.exception, [item.message for item in app.exception]
    assert app.session_state["explore_page"] == page
    return app
