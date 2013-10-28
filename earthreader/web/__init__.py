import collections
import datetime
import hashlib
import os.path
try:
    import urllib2
except ImportError:
    import urllib.request as urllib2

from flask import Flask, jsonify, render_template, request, url_for
from libearth.codecs import Rfc3339
from libearth.compat import binary
from libearth.feed import Feed
from libearth.feedlist import (Feed as FeedOutline,
                               FeedCategory as CategoryOutline, FeedList)
from libearth.parser.autodiscovery import autodiscovery, FeedUrlNotFoundError
from libearth.parser.heuristic import get_format
from libearth.schema import read, write
from libearth.tz import now

from .wsgi import MethodRewriteMiddleware


app = Flask(__name__)
app.wsgi_app = MethodRewriteMiddleware(app.wsgi_app)


app.config.update(dict(
    OPML='earthreader.opml',
    ALLFEED='All Feeds',
))


def feedlist_exists():
    REPOSITORY = app.config['REPOSITORY']
    OPML = app.config['OPML']
    if not os.path.isfile(os.path.join(REPOSITORY, OPML)):
        return False
    return True


def get_feedlist():
    REPOSITORY = app.config['REPOSITORY']
    OPML = app.config['OPML']
    if not os.path.isfile(os.path.join(REPOSITORY, OPML)):
        if not os.path.isdir(REPOSITORY):
            os.mkdir(REPOSITORY)
        feed_list = FeedList()
        feed_list.save_file(os.path.join(REPOSITORY, OPML))
    feed_list = FeedList(os.path.join(REPOSITORY, OPML))
    return feed_list


iterators = {}


def tidy_iterators_up():
    global iterators
    lists = []
    for key, pair in iterators.items():
        lists.append((key, pair))
    lists.sort(key=lambda pair: pair[1][1], reverse=True)
    for key, (it, time_saved) in lists:
        if time_saved < now() - datetime.timedelta(minutes=30):
            lists = lists[:lists.index((it, time_saved))]
    if len(lists) > 10:
        lists = lists[:10]
    iterators = dict(lists)


def get_entries(feed_list, category_id):
    tidy_iterators_up()
    REPOSITORY = app.config['REPOSITORY']
    url_token = request.args.get('url_token')
    feed_title = None
    it = None
    if url_token:
        pair = iterators.get(url_token)
        if pair:
            it = pair[0]
    if not it:
        feed_permalinks = {}
        sorting_pool = []
        for feed_id in feed_list:
            with open(os.path.join(REPOSITORY, feed_id + '.xml')) as f:
                feed = read(Feed, f)
                feed_permalink = feed_permalinks.get(feed_id)
                if not feed_permalink:
                    for link in feed.links:
                        if link.relation == 'alternate' and \
                                link.mimetype == 'text/html':
                            feed_permalinks[feed_id] = link.uri
                            feed_permalink = link.uri
                    if not feed_permalink:
                        feed_permalinks[feed_id] = feed.id
                        feed_permalink = feed.id
                for entry in feed.entries:
                    sorting_pool.append((feed.title, feed_id,
                                        feed_permalink, entry))
        sorting_pool.sort(key=lambda entry: entry[3].updated_at,
                          reverse=True)
        it = iter(sorting_pool)
        if not url_token:
            url_token = now().__str__()
        iterators[url_token] = it, now()
    entry_after = None
    entry_after = request.args.get('entry_after')
    next_key = None
    if entry_after:
        next_key = Rfc3339().decode(entry_after.replace(' ', 'T'))
    entries = []
    while len(entries) < 20:
        try:
            feed_title, feed_id, feed_permalink, entry = next(it)
        except StopIteration:
            iterators.pop(url_token)
            break
        if next_key and entry.updated_at > next_key:
            continue
        entry_permalink = None
        for link in entry.links:
            if link.relation == 'alternate' and \
                    link.mimetype == 'text/html':
                entry_permalink = link.uri
        if not entry_permalink:
            entry_permalink = entry.id
        entries.append({
            'title': entry.title,
            'entry_url': url_for(
                'feed_entry',
                category_id=category_id,
                feed_id=feed_id,
                entry_id=get_hash(entry.id),
                _external=True
            ),
            'permalink': entry_permalink or None,
            'updated': entry.updated_at.__str__(),
            'feed': {
                'title': feed_title,
                'entries_url': url_for(
                    'feed_entries',
                    feed_id=feed_id
                ),
                'permalink': feed_permalink or None
            }
        })
    return feed_title if len(feed_list) == 1 else None, entries, url_token


def get_hash(name):
    return hashlib.sha1(binary(name)).hexdigest()


def get_all_feeds(category, path=None):
    feeds = []
    categories = []
    if not path:
        feed_path = '/'
    else:
        feed_path = path
    for child in category:
        if isinstance(child, FeedOutline):
            feed_id = get_hash(child.xml_url)
            feeds.append({
                'title': child.title,
                'entries_url': url_for(
                    'feed_entries',
                    category_id=feed_path,
                    feed_id=feed_id,
                    _external=True
                ),
                'remove_feed_url': url_for(
                    'delete_feed',
                    category_id=feed_path,
                    feed_id=feed_id,
                    _external=True
                )
            })
        elif isinstance(child, CategoryOutline):
            categories.append({
                'title': child.title,
                'feeds_url': url_for(
                    'feeds',
                    category_id=feed_path + '/-' + child.title
                    if path else '-' + child.title,
                    _external=True
                ),
                'entries_url': url_for(
                    'category_entries',
                    category_id=feed_path + '/-' + child.title
                    if path else '-' + child.title,
                    _external=True
                ),
                'add_feed_url': url_for(
                    'add_feed',
                    category_id=feed_path + '/-' + child.title
                    if path else '-' + child.title,
                    _external=True
                ),
                'add_category_url': url_for(
                    'add_category',
                    category_id=feed_path + '/-' + child.title
                    if path else '-' + child.title,
                    _external=True
                ),
                'remove_category_url': url_for(
                    'delete_category',
                    category_id=feed_path + '/-' + child.title
                    if path else '-' + child.title,
                    _external=True
                ),
            })
    return feeds, categories


def check_path_valid(category_id, return_category_parent=False):
    if category_id == '/':
        feed_list = get_feedlist()
        return feed_list, feed_list, None
    if return_category_parent:
        category_list = category_id.split('/')
        target = category_list.pop()[1:]
        categories = collections.deque([category[1:] for category
                                       in category_list])
    else:
        target = None
        categories = collections.deque([category[1:] for category in
                                       category_id.split('/')])
    feed_list = get_feedlist()
    cursor = feed_list
    while categories:
        is_searched = False
        looking_for = categories.popleft()
        for category in cursor:
            if category.text == looking_for:
                is_searched = True
                cursor = category
                break
        if not is_searched:
            return None, None, None
    return feed_list, cursor, target


def find_feed_in_opml(feed_id, category, parent_categories=[], result=[]):
    categories = []
    if parent_categories:
        feed_path = '/'.join(parent_categories)
    else:
        feed_path = '/'
    for child in category:
        if isinstance(child, FeedOutline):
            current_feed_id = hashlib.sha1(binary(child.xml_url)).hexdigest()
            if current_feed_id == feed_id:
                result.append(feed_path)
        elif isinstance(child, CategoryOutline):
            categories.append(child)
    for category in categories:
        find_feed_in_opml(
            feed_id,
            category,
            parent_categories.append(category.title)
            if parent_categories else [category.title],
            result
        )
    return result


@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/feeds/', defaults={'category_id': '/'})
@app.route('/<path:category_id>/feeds/')
def feeds(category_id):
    feed_list, cursor, _ = check_path_valid(category_id)
    if not isinstance(feed_list, FeedList):
        r = jsonify(
            error='category-path-invalid',
            message='Given category path is not valid'
        )
        r.status_code = 404
        return r
    feeds, categories = get_all_feeds(cursor, category_id)
    return jsonify(feeds=feeds, categories=categories)


@app.route('/feeds/', methods=['POST'], defaults={'category_id': '/'})
@app.route('/<path:category_id>/feeds/', methods=['POST'])
def add_feed(category_id):
    REPOSITORY = app.config['REPOSITORY']
    feed_list, cursor, _ = check_path_valid(category_id)
    if (not isinstance(cursor, CategoryOutline) and
            not isinstance(cursor, FeedList)):
        r = jsonify(
            error='category-path-invalid',
            message='Given category path is not valid'
        )
        r.status_code = 404
        return r
    try:
        url = request.form['url']
        f = urllib2.urlopen(url)
        document = f.read()
    except ValueError:
        r = jsonify(
            error='unreachable-url',
            message='Cannot connect to given url'
        )
        r.status_code = 400
        return r
    try:
        feed_links = autodiscovery(document, url)
    except FeedUrlNotFoundError:
        r = jsonify(
            error='unreachable-feed-url',
            message='Cannot find feed url'
        )
        r.status_code = 400
        return r
    feed_url = feed_links[0].url
    if not feed_url == url:
        f.close()
        f = urllib2.urlopen(feed_url)
        xml = f.read()
    else:
        xml = document
    format = get_format(xml)
    result = format(xml, feed_url)
    feed = result[0]
    outline = FeedOutline('atom', feed.title.value, feed_url)
    for link in feed.links:
            if link.relation == 'alternate' and \
                    link.mimetype == 'text/html':
                outline.blog_url = link.uri
    cursor.append(outline)
    feed_list.save_file()
    file_name = get_hash(feed_url) + '.xml'
    with open(os.path.join(REPOSITORY, file_name), 'w') as f:
        for chunk in write(feed, indent='    ', canonical_order=True):
            f.write(chunk)
    return feeds(category_id)


@app.route('/', methods=['POST'], defaults={'category_id': '/'})
@app.route('/<path:category_id>/', methods=['POST'])
def add_category(category_id):
    feed_list, cursor, _ = check_path_valid(category_id)
    if (not isinstance(cursor, CategoryOutline) and
            not isinstance(cursor, FeedList)):
        r = jsonify(
            error='category-path-invalid',
            message='Given category path is not valid'
        )
        r.status_code = 404
        return r

    title = request.form['title']
    outline = CategoryOutline(title)
    cursor.append(outline)
    feed_list.save_file()
    return feeds(category_id)


@app.route('/<path:category_id>/', methods=['DELETE'])
def delete_category(category_id):
    feed_list, cursor, target = check_path_valid(category_id, True)
    if not cursor:
        r = jsonify(
            error='category-path-invalid',
            message='Given category path is not valid'
        )
        r.status_code = 404
        return r
    for child in cursor:
        if isinstance(child, CategoryOutline):
            if child.text == target:
                cursor.remove(child)
    feed_list.save_file()
    index = category_id.rfind('/')
    if index == -1:
        return feeds('/')
    else:
        return feeds(category_id[:index])


@app.route('/feeds/<feed_id>/', methods=['DELETE'],
           defaults={'category_id': '/'})
@app.route('/<path:category_id>/feeds/<feed_id>/', methods=['DELETE'])
def delete_feed(category_id, feed_id):
    REPOSITORY = app.config['REPOSITORY']
    feed_list, cursor, _ = check_path_valid(category_id)
    if not cursor:
        r = jsonify(
            error='category-path-invalid',
            message='Given category path is not valid'
        )
        r.status_code = 404
        return r
    target = None
    for feed in cursor:
        if isinstance(feed, FeedOutline):
            if feed_id == hashlib.sha1(binary(feed.xml_url)).hexdigest():
                target = feed
    if target:
        cursor.remove(target)
    else:
        r = jsonify(
            error='feed-not-found-in-path',
            message='Given feed does not exists in the path'
        )
        r.status_code = 400
        return r
    feed_list.save_file()
    if not find_feed_in_opml(feed_id, feed_list):
        os.remove(os.path.join(REPOSITORY, feed_id + '.xml'))
    return feeds(category_id)


@app.route('/feeds/<feed_id>/entries/', defaults={'category_id': '/'})
@app.route('/<path:category_id>/feeds/<feed_id>/entries/')
def feed_entries(category_id, feed_id):
    if not check_path_valid(category_id)[0]:
        r = jsonify(
            error='category-path-invalid',
            message='Given category path is not valid'
        )
        r.status_code = 404
        return r
    feed_title, entries, url_token = get_entries([feed_id], category_id)
    if len(entries) < 20:
        next_url = None
    else:
        next_url = url_for(
            'feed_entries',
            category_id=category_id,
            feed_id=feed_id,
            url_token=url_token,
            entry_after=entries[-1]['updated'] if entries else None
        )
    return jsonify(
        title=feed_title,
        entries=entries,
        next_url=next_url
    )


@app.route('/entries/', defaults={'category_id': '/'})
@app.route('/<path:category_id>/entries/')
def category_entries(category_id):
    lst, cursor, target = check_path_valid(category_id)
    if not isinstance(lst, FeedList):
        r = jsonify(
            error='category-path-invalid',
            message='Given category was not found'
        )
        r.status_code = 404
        return r
    feed_list = []
    for child in cursor.get_all_feeds():
        feed_list.append(get_hash(child.xml_url))
    _, entries, url_token = get_entries(feed_list, category_id)
    if len(entries) < 20:
        next_url = None
    else:
        next_url = url_for(
            'category_entries',
            category_id=category_id,
            url_token=url_token,
            entry_after=entries[-1]['updated'] if entries else None
        )
    return jsonify(
        title=category_id.split('/')[-1][1:] or app.config['ALLFEED'],
        entries=entries,
        next_url=next_url
    )


@app.route('/feeds/<feed_id>/entries/<entry_id>/',
           defaults={'category_id': '/'})
@app.route('/<path:category_id>/feeds/<feed_id>/entries/<entry_id>/')
def feed_entry(category_id, feed_id, entry_id):
    if not check_path_valid(category_id)[0]:
        r = jsonify(
            error='category-path-invalid',
            message='Given category path is not valid'
        )
        r.status_code = 404
        return r
    REPOSITORY = app.config['REPOSITORY']
    try:
        with open(os.path.join(REPOSITORY, feed_id + '.xml')) as f:
            feed = read(Feed, f)
            feed_permalink = None
            for link in feed.links:
                if link.relation == 'alternate'\
                   and link.mimetype == 'text/html':
                    feed_permalink = link.uri
                if not feed_permalink:
                    feed_permalink = feed.id
            for entry in feed.entries:
                entry_permalink = None
                for link in entry.links:
                    if link.relation == 'alternate'\
                       and link.mimetype == 'text/html':
                        entry_permalink = link.uri
                if not entry_permalink:
                    entry_permalink = entry.id
                if entry_id == get_hash(entry.id):
                    return jsonify(
                        title=entry.title,
                        content=entry.content.sanitized_html
                        if entry.content else entry.summary.sanitized_html,
                        updated=entry.updated_at.__str__(),
                        permalink=entry_permalink or None,
                        feed={
                            'title': feed.title,
                            'entries_url': url_for(
                                'feed_entries',
                                feed_id=feed_id,
                                _external=True
                            ),
                            'permalink': feed_permalink or None
                        }
                    )
            r = jsonify(
                error='entry-not-found',
                message='Given entry does not exist'
            )
            r.status_code = 404
            return r

    except IOError:
        r = jsonify(
            error='feed-not-found',
            message='Given feed does not exist'
        )
        r.status_code = 404
        return r
