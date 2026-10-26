"""Exercise grouped navigation and existing shortcuts without a data library."""
import pytest
from streamlit.testing.v1 import AppTest


SCRIPT = """
import streamlit as st
from stats_app import dashboard_controls as controls
from stats_app.navigation import navigation_regions, render_navigation

include_optional = st.checkbox('Include optional collections', value=True, key='optional')
pages = ['Overview', 'Decision report', 'Spotify', 'YouTube collection',
         'Meta collection', 'Social', 'Shopify', 'Cross-platform', 'Data quality',
         'Snapshot explorer', 'Campaigns', 'Import data', 'Sources & provenance',
         'Coverage & cross-reference']
if not include_optional:
    pages = [page for page in pages if page not in ('YouTube collection', 'Meta collection', 'Shopify')]
primary, secondary, more = navigation_regions()
page = render_navigation(pages, primary, secondary)
st.caption('Current page: ' + page)
if page == 'Spotify':
    controls.selectbox('Spotify period', ['Latest 28 days', 'Latest 90 days', 'All available'],
                       key='spotify:preset')
elif page == 'Decision report':
    controls.selectbox('Decision period', ['Latest 28 days', 'Latest 90 days', 'Custom'],
                       key='decision:preset')
controls.jump('Open Spotify shortcut', 'Spotify', key='jump_spotify',
              **{'spotify:preset': 'All available'})
controls.jump('Open decision shortcut', 'Decision report', key='jump_decision',
              **{'decision:preset': 'Custom'})
"""


@pytest.fixture
def app():
    result = AppTest.from_string(SCRIPT).run()
    assert not result.exception and not result.error
    return result


def assert_active(app, page):
    assert not app.exception and not app.error
    assert app.session_state['explore_page'] == page
    active = [item.key for item in app.sidebar.button if item.proto.type == 'primary']
    assert active == ['nav:' + page]
    assert any(item.value == 'Current page: ' + page for item in app.caption)


def test_cross_group_selection_keeps_every_page_reachable_and_one_active(app):
    more = next(item for item in app.sidebar.expander if item.label == 'More')
    secondary_keys = {item.key for item in more.button}
    assert [item.label for item in app.sidebar.button if item.key not in secondary_keys] == [
        'Overview', 'Spotify', 'YouTube', 'Social', 'Shopify', 'Cross-platform']
    assert [item.label for item in more.button] == [
        'Decision report', 'Campaigns', 'Meta collection', 'Import data', 'Data quality',
        'Snapshot explorer', 'Sources & provenance', 'Coverage & cross-reference']
    assert not more.proto.expanded
    assert_active(app, 'Overview')

    app.button('nav:Campaigns').click().run()
    assert_active(app, 'Campaigns')
    assert next(item for item in app.expander if item.label == 'More').proto.expanded
    app.button('nav:YouTube collection').click().run()
    assert_active(app, 'YouTube collection')
    assert not next(item for item in app.expander if item.label == 'More').proto.expanded
    app.button('nav:Sources & provenance').click().run()
    assert_active(app, 'Sources & provenance')
    app.button('nav:Shopify').click().run()
    assert_active(app, 'Shopify')


def test_existing_shortcuts_target_both_groups_and_preserve_view_selections(app):
    app.button('jump_spotify').click().run()
    assert_active(app, 'Spotify')
    assert app.selectbox('control:spotify:preset').value == 'All available'
    app.selectbox('control:spotify:preset').set_value('Latest 90 days').run()

    app.button('jump_decision').click().run()
    assert_active(app, 'Decision report')
    assert app.selectbox('control:decision:preset').value == 'Custom'
    assert app.session_state['selection:spotify:preset'] == 'Latest 90 days'
    app.selectbox('control:decision:preset').set_value('Latest 90 days').run()

    app.button('nav:Spotify').click().run()
    assert_active(app, 'Spotify')
    assert app.selectbox('control:spotify:preset').value == 'Latest 90 days'
    app.button('nav:Decision report').click().run()
    assert_active(app, 'Decision report')
    assert app.selectbox('control:decision:preset').value == 'Latest 90 days'


def test_removed_optional_page_falls_back_after_source_change(app):
    for optional_page in ('YouTube collection', 'Meta collection', 'Shopify'):
        app.checkbox('optional').set_value(True).run()
        app.button('nav:' + optional_page).click().run()
        assert_active(app, optional_page)
        app.checkbox('optional').set_value(False).run()
        assert_active(app, 'Overview')
        available = {item.key for item in app.sidebar.button}
        assert 'nav:YouTube collection' not in available
        assert 'nav:Meta collection' not in available
        assert 'nav:Shopify' not in available
        assert {'nav:Spotify', 'nav:Campaigns', 'nav:Import data'} <= available
