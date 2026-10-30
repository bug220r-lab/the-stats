"""Native route stability, unavailable destinations and scoped view state."""
import pytest
from native_navigation_helpers import NativeAppTest as AppTest

from native_navigation_helpers import open_page
from stats_app.navigation import PAGE_GROUPS, PAGE_PATHS


SCRIPT = """
import streamlit as st
from stats_app import dashboard_controls as controls
from stats_app.navigation import run_navigation

available = st.checkbox('Optional source available', value=True, key='optional')
version = controls.selectbox('Analysis version', ['v1', 'v2'], key='analysis_version')
optional = {'Apple Music', 'YouTube collection', 'Linktree', 'Shopify', 'Meta collection'}

def render_page(page):
    controls.begin_view(page)
    st.caption('Current page: ' + page)
    if page in optional and not available:
        st.info('Source unavailable for ' + page + '; this destination remains reachable.')
    if page == 'Spotify':
        controls.selectbox('Spotify period', ['Latest 28 days', 'Latest 90 days', 'All available'], key='spotify:preset')
        controls.multiselect('Recordings · empty means all', ['one', 'two'] if version == 'v1' else ['one'], key='spotify:recordings')
    elif page == 'Decision report':
        controls.selectbox('Decision period', ['Latest 28 days', 'Latest 90 days', 'Custom'], key='decision:preset')
    elif page == 'Social':
        st.checkbox('Include partial source days', value=False, key='social-partial')
        st.checkbox('Include undated captures', value=True, key='social-content-undated')
        query = st.text_input('Raw social search', value=st.session_state.get('selection:social-content-search', ''), key='social-content-search')
        st.session_state['selection:social-content-search'] = query
        controls.multiselect('Content platforms', ['Instagram', 'Facebook'], default=['Instagram', 'Facebook'], key='content-library-platforms')
        controls.selectbox('Content identity', ['post-one', 'post-two'], key='content-library-inspect')
        controls.multiselect('Recordings · empty means all', ['one', 'two'], key='social-optional-recordings')
        controls.own_keys('content-library-rows:fixture', 'analysis_version')
        st.download_button('Download source', b'synthetic-only', 'source.txt', key='content-library-source-download')
    controls.reset_button(page)
    controls.finish_view()
    controls.jump('Open Spotify shortcut', 'Spotify', key='jump_spotify', **{'spotify:preset': 'All available'})
    controls.jump('Open decision shortcut', 'Decision report', key='jump_decision', **{'decision:preset': 'Custom'})

run_navigation(render_page)
"""


@pytest.fixture

def app():
    result = AppTest.from_string(SCRIPT).run()
    assert not result.exception and not result.error
    return result


def assert_active(app, page):
    assert not app.exception and not app.error
    assert app.session_state['explore_page'] == page
    assert any(item.value == 'Current page: ' + page for item in app.caption)
    assert not any(item.key and item.key.startswith('nav:') for item in app.button)


def route_map(app):
    return {name: (page.url_path, page.title) for name, page in app.session_state['_native_routes'].items()}


def test_all_destinations_have_unique_stable_native_routes_and_render_only_one_page(app):
    expected_names = [name for names in PAGE_GROUPS.values() for name in names]
    assert expected_names == list(PAGE_PATHS)
    initial = route_map(app)
    assert set(initial) == set(expected_names)
    assert len({path for path, _ in initial.values()}) == len(expected_names)
    assert initial['Overview'][0] == ''  # Streamlit's default page is the root URL.
    assert initial['YouTube collection'] == ('youtube', 'YouTube')
    for page in expected_names:
        assert initial[page][0] == ('' if page == 'Overview' else PAGE_PATHS[page])
        open_page(app, page)
        assert_active(app, page)
        assert len([item for item in app.caption if item.value.startswith('Current page:')]) == 1
        assert route_map(app) == initial


def test_existing_shortcuts_target_both_groups_and_preserve_view_selections(app):
    app.button('jump_spotify').click().run()
    assert_active(app, 'Spotify')
    assert app.selectbox('control:spotify:preset').value == 'All available'
    app.selectbox('control:spotify:preset').set_value('Latest 90 days').run()
    app.multiselect('control:spotify:recordings').set_value(['two']).run()
    app.button('jump_decision').click().run()
    assert_active(app, 'Decision report')
    assert app.selectbox('control:decision:preset').value == 'Custom'
    assert app.session_state['selection:spotify:preset'] == 'Latest 90 days'
    app.selectbox('control:decision:preset').set_value('Latest 90 days').run()
    open_page(app, 'Spotify')
    assert_active(app, 'Spotify')
    assert app.selectbox('control:spotify:preset').value == 'Latest 90 days'
    assert app.multiselect('control:spotify:recordings').value == ['two']
    open_page(app, 'Decision report')
    assert app.selectbox('control:decision:preset').value == 'Latest 90 days'


def test_source_changes_keep_unavailable_routes_reachable_and_current(app):
    initial = route_map(app)
    for page in ('Apple Music', 'YouTube collection', 'Linktree', 'Shopify', 'Meta collection'):
        app.checkbox('optional').set_value(True).run()
        open_page(app, page)
        app.checkbox('optional').set_value(False).run()
        assert_active(app, page)
        assert any('Source unavailable for ' + page in item.value for item in app.info)
        assert route_map(app) == initial


def test_reset_affects_only_current_view_and_preserves_source_and_other_view(app):
    app.selectbox('control:analysis_version').set_value('v2').run()
    open_page(app, 'Decision report')
    app.selectbox('control:decision:preset').set_value('Custom').run()
    open_page(app, 'Spotify')
    app.selectbox('control:spotify:preset').set_value('All available').run()
    app.multiselect('control:spotify:recordings').set_value(['one']).run()
    app.button('reset:Spotify').click().run()
    assert_active(app, 'Spotify')
    assert app.selectbox('control:spotify:preset').value == 'Latest 28 days'
    assert app.multiselect('control:spotify:recordings').value == []
    assert app.selectbox('control:analysis_version').value == 'v2'
    assert app.session_state['selection:decision:preset'] == 'Custom'


def test_source_change_removes_only_recording_options_absent_from_new_source(app):
    open_page(app, 'Spotify')
    app.selectbox('control:spotify:preset').set_value('Latest 90 days').run()
    app.multiselect('control:spotify:recordings').set_value(['one', 'two']).run()
    app.selectbox('control:analysis_version').set_value('v2').run()
    assert_active(app, 'Spotify')
    assert app.multiselect('control:spotify:recordings').value == ['one']
    assert app.selectbox('control:spotify:preset').value == 'Latest 90 days'
    assert any('absent from this source were removed' in item.value for item in app.caption)


def test_unknown_requested_route_does_not_execute_an_unregistered_destination(app):
    open_page(app, 'Campaigns')
    app.session_state['_requested_page'] = '../unknown'
    app.run()
    assert_active(app, 'Campaigns')


def test_social_reset_clears_raw_filters_and_detail_targets_without_restoring_download_bools(app):
    app.selectbox('control:analysis_version').set_value('v2').run()
    open_page(app, 'Social')
    app.checkbox('social-partial').set_value(True).run()
    app.checkbox('social-content-undated').set_value(False).run()
    app.text_input('social-content-search').set_value('saved search').run()
    app.selectbox('control:content-library-inspect').set_value('post-two').run()
    app.multiselect('control:content-library-platforms').set_value([]).run()
    summaries = app.session_state['_view_filter_summaries']['Social']
    assert summaries['content-library-platforms'].endswith('None selected')
    assert summaries['social-optional-recordings'].endswith('All available')
    saved = app.session_state['_legacy_view_selections']['Social']
    assert saved['social-partial'] is True and saved['social-content-undated'] is False
    assert 'content-library-source-download' not in saved
    app.session_state['content-library-rows:fixture'] = {'selection': {'rows': [1]}}
    open_page(app, 'Overview')
    open_page(app, 'Social')
    assert app.checkbox('social-partial').value is True
    assert app.checkbox('social-content-undated').value is False
    assert app.text_input('social-content-search').value == 'saved search'
    assert app.selectbox('control:content-library-inspect').value == 'post-two'
    app.button('reset:Social').click().run()
    assert not app.exception
    assert app.checkbox('social-partial').value is False
    assert app.checkbox('social-content-undated').value is True
    assert app.text_input('social-content-search').value == ''
    assert app.selectbox('control:content-library-inspect').value == 'post-one'
    assert app.multiselect('control:content-library-platforms').value == ['Instagram', 'Facebook']
    assert app.selectbox('control:analysis_version').value == 'v2'
    assert 'content-library-rows:fixture' not in app.session_state
