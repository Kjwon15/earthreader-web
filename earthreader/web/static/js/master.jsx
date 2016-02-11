var Feed = React.createClass({
  handleOnClick: function(event) {
    event.preventDefault();
    selectFeed(this.props.data.entries_url, this.props.data.title);
  },
  render: function() {
    return (
        <a className="mdl-navigation__link" href={this.props.data.entries_url}
        onClick={ this.handleOnClick }>
        {this.props.data.title}
        </a>
        );
  }
});

var Feeds = React.createClass({
  getInitialState: function() {
    try {
      var url = this.props.data.entries_url;
    } catch(e) {
      var url = URLS.entries;
    }
    return {
      url: url,
      categories: [],
      feeds: [],
    };
  },
  handleOnClick: function(event) {
    event.preventDefault();
    selectFeed(this.state.url, this.props.data.title);
  },
  getFeedsFromServer: function() {
    try {
      var url = this.props.data.feeds_url;
    } catch(e) {
      var url = this.props.url;
    }
    $.ajax({
      url: url,
      dataType: 'json',
      cache: false,
      success: function(data) {
        this.setState({categories: data.categories, feeds: data.feeds});
      }.bind(this),
      error: function(xhr, status, err) {
        console.error(url, status, error.toString());
      }.bind(this)
    });
  },
  componentDidMount: function() {
    this.getFeedsFromServer();
  },
  render: function() {
    var categories = this.state.categories.map(function(category) {
      return (<Feeds data={category} key={category.path} />);
    });
    var feeds = this.state.feeds.map(function(feed) {
      return (<Feed data={feed} key={feed.path} />);
    });
    try {
      var title = this.props.data.title;
    } catch(e) {
      var title = 'All';
    }
    return (
        <div className="feeds">
        <a className="mdl-navigation__link" href={this.state.url}
        onClick={ this.handleOnClick }>{ title }</a>
        { categories }
        { feeds }
        </div>
        );
  }
});

var Entries = React.createClass({
  getInitialState: function() {
    return {
      entries: [],
      title: this.props.title,
    };
  },
  getEntriesFromServer: function() {
    $.ajax({
      url: this.props.url,
      dataType: 'json',
      success: function(data) {
        this.setState(data);
      }.bind(this),
      error: function(xhr, status, err) {
         console.error(this.props.url, status, err.toString());
      }.bind(this)
    })
  },
  componentDidMount: function() {
    this.getEntriesFromServer();
  },
  render: function() {
    var entries = this.state.entries.map(function(entry) {
      return (<Entry data={entry} key={entry.entry_id} />)
    });
    return (
        <div className="entries">
          <h3>{ this.state.title }</h3>
          { entries }
        </div>
        );
  }
});

var Entry = React.createClass({
  getInitialState: function() {
    return {
      entryContent: '',
    };
  },
  handleExpandEntry: function(event) {
    event.preventDefault();
    this.setState({
      entryContent: 'cake',
    })
  },
  render: function() {
    var star = this.props.data.starred;
    var menuId = "entry-menu-" + this.props.data.entry_id;
    return (
        <section className="entry mdl-grid">
          <article className="mdl-card mdl-cell mdl-cell--12-col mdl-shadow--2dp">
            <div className="mdl-card__title">
              <h2 className="mdl-card__title-text">{ this.props.data.title }</h2>
              <h3 className="mdl-card__subtitle-text">{ this.props.data.feed.title }</h3>
            </div>
            <div className="mdl-card__supporting-text">
              <time>{ this.props.data.updated }</time>
            </div>
            <div className="mdl-card__supporting-text" dangerouslySetInnerHTML={ {__html: this.state.entryContent} }>
            </div>
            <div className="mdl-card__actions mdl-card--border">
              <a href={ this.props.data.entry_url } onClick={ this.handleExpandEntry }>
                <button className="mdl-button mdl-js-button mdl-button--raised">
                  Read
                  <i className="material-icons">arrow_forward</i>
                </button>
              </a>
            </div>
          </article>
        </section>
        );
    return (
        <article className="entry">
        <div className="entry-title">{ this.props.data.title }</div>
        </article>
        );
  }
});

ReactDOM.render(
    <Feeds url={ URLS.feeds } />,
    document.querySelector('#feedList')
    );


var entries = React.createElement(Entries, {url: URLS.entries, title: 'All feeds'});
ReactDOM.render(
    entries,
    document.querySelector('.mdl-layout__content')
    );

function selectFeed(url, title) {
  var domContainerNode = document.querySelector('.mdl-layout__content');
  ReactDOM.unmountComponentAtNode(domContainerNode);
  entries = React.createElement(Entries, {url: url, title: title});
  ReactDOM.render(entries, domContainerNode);
}
