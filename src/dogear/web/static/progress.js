// Keeps a book's page up to date while it is read or made. Without this script the
// page still works: its "Check progress" link reloads it.
//
// Every few seconds it asks the server for the book's status. It changes the status
// region (role="status") only when the sentence is different, so a screen reader never
// hears the same news twice, and adds new progress lines to the list without announcing
// them. When the book moves on (made, stopped, or read), it says so and stops asking.
(function () {
  "use strict";

  var EVERY_MS = 4000;
  var AFTER_ERROR_MS = 15000;

  var box = document.getElementById("book-status");
  var region = document.getElementById("status");
  if (!box || !region || !box.dataset.statusUrl || !window.fetch) {
    return;
  }
  var continues = (box.dataset.continues || "").split(" ");
  var lines = document.getElementById("progress-lines");
  var link = document.getElementById("check-progress");
  var shown = lines ? Number(lines.getAttribute("start") || 1) - 1 + lines.children.length : 0;

  function addLines(status) {
    if (!lines) {
      return;
    }
    // status.first is the number of lines before status.lines[0].
    for (var i = Math.max(0, shown - status.first); i < status.lines.length; i++) {
      var item = document.createElement("li");
      item.textContent = status.lines[i];
      lines.appendChild(item);
    }
    shown = Math.max(shown, status.first + status.lines.length);
  }

  function say(text) {
    if (region.textContent !== text) {
      region.textContent = text;
    }
  }

  function update(status) {
    addLines(status);
    document.title = status.title;
    if (continues.indexOf(status.state) !== -1) {
      say(status.sentence);
      return true;
    }
    say(status.sentence + " " + box.dataset.changed);
    if (link) {
      link.textContent = box.dataset.changedLink;
    }
    return false;
  }

  function ask() {
    fetch(box.dataset.statusUrl, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("status " + response.status);
        }
        return response.json();
      })
      .then(function (status) {
        if (update(status)) {
          window.setTimeout(ask, EVERY_MS);
        }
      })
      .catch(function () {
        // Dogear may have been stopped; try again less often, and say nothing.
        window.setTimeout(ask, AFTER_ERROR_MS);
      });
  }

  window.setTimeout(ask, EVERY_MS);
})();
