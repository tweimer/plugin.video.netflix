# -*- coding: utf-8 -*-
"""Helper functions for setting infolabels of list items"""
from __future__ import unicode_literals

import resources.lib.common as common
import resources.lib.cache as cache
import resources.lib.api.paths as paths
import resources.lib.kodi.library as library


def add_info(videoid, list_item, item, raw_data):
    """Add infolabels to the list_item. The passed in list_item is modified
    in place and the infolabels are returned."""
    # pylint: disable=too-many-locals
    try:
        cache_entry = cache.get(cache.CACHE_INFOLABELS, videoid)
        infos = cache_entry['infos']
        quality_infos = cache_entry['quality_infos']
    except cache.CacheMiss:
        infos, quality_infos = parse_info(videoid, item, raw_data)
        cache.add(cache.CACHE_INFOLABELS,
                  videoid,
                  {'infos': infos, 'quality_infos': quality_infos},
                  ttl=common.CACHE_METADATA_TTL, to_disk=True)
    list_item.setInfo('video', infos)
    if infos['mediatype'] in ['episode', 'movie']:
        list_item.setProperty('IsPlayable', 'true')
    for stream_type, quality_infos in quality_infos.iteritems():
        list_item.addStreamInfo(stream_type, quality_infos)
    return infos


def add_art(videoid, list_item, item, raw_data=None):
    """Add art infolabels to list_item"""
    try:
        art = cache.get(cache.CACHE_ARTINFO, videoid)
    except cache.CacheMiss:
        art = parse_art(videoid, item, raw_data)
        cache.add(cache.CACHE_ARTINFO, videoid, art,
                  ttl=common.CACHE_METADATA_TTL, to_disk=True)
    list_item.setArt(art)
    return art


def add_info_for_playback(videoid, list_item):
    """Retrieve infolabels and art info and add them to the list_item"""
    try:
        return add_info_from_library(videoid, list_item)
    except library.ItemNotFound:
        return add_info_from_netflix(videoid, list_item)


def parse_info(videoid, item, raw_data):
    """Parse info from a path request response into Kodi infolabels"""
    if (videoid.mediatype == common.VideoId.UNSPECIFIED and
            hasattr(item, 'contained_titles')):
        # Special handling for VideoLists
        return {
            'mediatype': 'video',
            'plot': common.get_local_string(30087).format(
                ', '.join(item.contained_titles))
        }, {}

    infos = {'mediatype': ('tvshow'
                           if videoid.mediatype == common.VideoId.SHOW
                           else videoid.mediatype)}
    if videoid.mediatype in [common.VideoId.SHOW, common.VideoId.SEASON,
                             common.VideoId.EPISODE]:
        infos['tvshowtitle'] = raw_data['videos'][videoid.tvshowid]['title']

    parse_atomic_infos(item, infos)
    parse_referenced_infos(item, infos, raw_data)

    infos['tag'] = [tagdef['name']
                    for tagdef
                    in item.get('tags', {}).itervalues()
                    if isinstance(tagdef.get('name', {}), unicode)]

    return infos, get_quality_infos(item)


def parse_atomic_infos(item, infos):
    """Parse those infos into infolabels that are directly accesible from
    the item dict"""
    for target, source in paths.INFO_MAPPINGS.iteritems():
        value = (common.get_path_safe(source, item)
                 if isinstance(source, list)
                 else item.get(source))
        if isinstance(value, dict):
            value = None
        if value is None:
            common.debug('Infolabel {} not available'.format(target))
            continue
        if target in paths.INFO_TRANSFORMATIONS:
            value = paths.INFO_TRANSFORMATIONS[target](value)
        infos[target] = value
    return infos


def parse_referenced_infos(item, infos, raw_data):
    """Parse those infos into infolabels that need their references
    resolved within the raw data"""
    for target, source in paths.REFERENCE_MAPPINGS.iteritems():
        infos[target] = [
            person['name']
            for _, person
            in paths.resolve_refs(item.get(source, {}), raw_data)]
    return infos


def get_quality_infos(item):
    """Return audio and video quality infolabels"""
    quality_infos = {}
    delivery = item.get('delivery')
    if delivery:
        if delivery.get('hasHD'):
            quality_infos['video'] = {'codec': 'h264', 'width': '1920',
                                      'height': '1080'}
        elif delivery.get('hasUltraHD'):
            quality_infos['video'] = {'codec': 'h265', 'width': '3840',
                                      'height': '2160'}
        else:
            quality_infos['video'] = {'codec': 'h264', 'width': '960',
                                      'height': '540'}
            # quality_infos = {'width': '1280', 'height': '720'}
        if delivery.get('has51Audio'):
            quality_infos['audio'] = {'channels': 6}
        else:
            quality_infos['audio'] = {'channels': 2}

        quality_infos['audio']['codec'] = (
            'eac3'
            if common.ADDON.getSettingBool('enable_dolby_sound')
            else 'aac')
    return quality_infos


def parse_art(videoid, item, raw_data):
    """Parse art info from a path request response to Kodi art infolabels"""
    boxarts = common.get_multiple_paths(
        paths.ART_PARTIAL_PATHS[0] + ['url'], item)
    interesting_moment = common.get_multiple_paths(
        paths.ART_PARTIAL_PATHS[1] + ['url'], item)[paths.ART_SIZE_FHD]
    clearlogo = common.get_path_safe(
        paths.ART_PARTIAL_PATHS[3] + ['url'], item)
    fanart = common.get_path_safe(
        paths.ART_PARTIAL_PATHS[4] + [0, 'url'], item)
    return assign_art(videoid,
                      boxarts[paths.ART_SIZE_FHD],
                      boxarts[paths.ART_SIZE_SD],
                      boxarts[paths.ART_SIZE_POSTER],
                      interesting_moment,
                      clearlogo,
                      fanart)


def assign_art(videoid, boxart_large, boxart_small, poster, interesting_moment,
               clearlogo, fanart):
    """Assign the art available from Netflix to appropriate Kodi art"""
    # pylint: disable=too-many-arguments
    art = {}
    art['poster'] = poster or ''
    art['clearlogo'] = (clearlogo
                        if videoid.mediatype != common.VideoId.UNSPECIFIED
                        else '') or ''
    art['thumb'] = ((interesting_moment
                     if videoid.mediatype == common.VideoId.EPISODE else '') or
                    boxart_large or
                    boxart_small)
    art['landscape'] = art['thumb']
    art['fanart'] = (fanart or
                     interesting_moment or
                     boxart_large or
                     boxart_small or
                     '')
    return art


def add_info_from_netflix(videoid, list_item):
    """Apply infolabels with info from Netflix API"""
    try:
        infos = add_info(videoid, list_item, None, None)
        art = add_art(videoid, list_item, None)
        common.debug('Got infolabels and art from cache')
    except TypeError:
        common.info('Infolabels or art were not in cache, retrieving from API')
        import resources.lib.api.shakti as api
        api_data = api.single_info(videoid)
        infos = add_info(videoid, list_item, api_data['videos'][videoid],
                         api_data)
        art = add_art(videoid, list_item, api_data['videos'][videoid])
    return infos, art


def add_info_from_library(videoid, list_item):
    """Apply infolabels with info from Kodi library"""
    details = library.get_item(videoid, include_props=True)
    art = details.pop('art', {})
    infos = {
        'DBID': details.pop('id'),
        'mediatype': details['type'],
        'DBTYPE': details.pop('type')
    }
    infos.update(details)
    list_item.setInfo(infos)
    list_item.setArt(art)
    return infos, art