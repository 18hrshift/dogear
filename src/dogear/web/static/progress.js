// Keeps a book's page up to date while it is read or made. Without this script the
// page still works: its "Check progress" link reloads it.
//
// Every few seconds it asks the server for the book's status. It changes the status
// region (role="status") only when the sentence is different, so a screen reader never
// hears the same news twice, and adds new progress lines to the list without announcing
// them. When the book moves on (made, stopped, or read), it says so and stops asking.
//
// The status carries only the latest lines. A line repeated in a row is one line with a
// count, so the last lines shown may change ("(3 times)" becomes "(4 times)"). The list
// keeps at most as many lines as the page shows, and says how many came before them.
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
  var leftOut = document.getElementById("lines-left-out");
  var link = document.getElementById("check-progress");
  // The number of lines before the first one in the list.
  var first = lines ? Number(lines.getAttribute("start") || 1) - 1 : 0;
  var maxLines = lines ? Number(lines.dataset.maxLines || 0) : 0;

  function startAt(number) {
    first = number;
    lines.setAttribute("start", String(number + 1));
    if (leftOut) {
      var many = (lines.dataset.leftOutMany || "").replace("{n}", number.toLocaleString("en-US"));
      leftOut.textContent = number === 1 ? lines.dataset.leftOutOne : many;
      leftOut.hidden = number === 0;
    }
  }

  function addLines(status) {
    if (!lines) {
      return;
    }
    // status.first is the number of lines before status.lines[0].
    var end = first + lines.children.length;
    if (status.first > end) {
      // More lines came than one status carries: start the list again from these.
      lines.textContent = "";
      startAt(status.first);
      end = status.first;
    }
    for (var i = 0; i < status.lines.length; i++) {
      var number = status.first + i;
      if (number < first) {
        continue;
      }
      if (number < end) {
        var shown = lines.children[number - first];
        if (shown.textContent !== status.lines[i]) {
          shown.textContent = status.lines[i];
        }
      } else {
        var item = document.createElement("li");
        item.textContent = status.lines[i];
        lines.appendChild(item);
      }
    }
    var removed = 0;
    while (maxLines && lines.children.length > maxLines) {
      lines.removeChild(lines.firstElementChild);
      removed++;
    }
    if (removed) {
      startAt(first + removed);
    }
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
