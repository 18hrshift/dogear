// Plays a Listen in place, on the page where Listen was pressed. Without this script the
// page still works: Listen sends its form, and the page that comes back has a player.
//
// A Listen form names its status region (role="status") in data-listen. This sends the
// form asking for JSON, asks how it's going until the recording is ready, then plays it
// in a player put just before the region, named "Recording of" the text. The region
// says "Getting it ready" when Listen is pressed, and what went wrong if something does.
// It changes only when the words are different, so a screen reader never hears the same
// news twice. Nothing plays until Listen is pressed.
//
// Nothing is announced as the recording starts or ends. A recording is often a single
// word, about a second long: anything said as it starts would be spoken over it, and
// anything said as it ends would only follow what the listener has just heard. So the
// region is emptied as playing starts (emptying it isn't announced), which also keeps
// "Getting it ready" from staying on screen while it plays.
(function () {
  "use strict";

  var EVERY_MS = 700;
  var NO_ANSWER = "Dogear didn't answer. Check that it's still running, then choose Listen again.";
  var PRESS_PLAY = "Ready. Use the player's Play button to hear it.";
  var CANT_PLAY = "This browser couldn't play the recording.";

  if (!window.fetch || !window.FormData || !window.URLSearchParams) {
    return;
  }

  function say(region, text) {
    if (region.textContent !== text) {
      region.textContent = text;
    }
  }

  function json(response) {
    var type = response.headers.get("Content-Type") || "";
    if (type.indexOf("application/json") === -1) {
      throw new Error("not JSON");
    }
    return response.json();
  }

  function player(region) {
    var id = region.id + "-player";
    var audio = document.getElementById(id);
    if (!audio) {
      audio = document.createElement("audio");
      audio.id = id;
      audio.controls = true;
      audio.preload = "auto";
      audio.addEventListener("playing", function () {
        say(region, "");
      });
      audio.addEventListener("error", function () {
        say(region, CANT_PLAY);
      });
      region.parentNode.insertBefore(audio, region);
    }
    return audio;
  }

  function play(region, status) {
    var audio = player(region);
    audio.setAttribute("aria-label", "Recording of " + status.text);
    audio.src = status.audio_url;
    var started = audio.play();
    if (started && started.catch) {
      started.catch(function (error) {
        if (error && error.name === "NotAllowedError") {
          // The browser wants a press on the player itself.
          say(region, PRESS_PLAY);
        }
        // Any other failure to play fires the player's error event, which says so.
      });
    }
  }

  function failed(region, status) {
    var why = [status.error, status.hint].filter(Boolean).join(" ");
    say(region, why || "Dogear couldn't say it.");
  }

  function follow(form, region, status) {
    if (status.state === "done") {
      play(region, status);
      form.removeAttribute("data-busy");
      return;
    }
    if (status.state === "failed") {
      failed(region, status);
      form.removeAttribute("data-busy");
      return;
    }
    // Still "Getting it ready.": one announcement until it plays.
    window.setTimeout(function () {
      fetch(status.status_url, { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(json)
        .then(function (next) {
          follow(form, region, next);
        })
        .catch(function () {
          say(region, NO_ANSWER);
          form.removeAttribute("data-busy");
        });
    }, EVERY_MS);
  }

  document.addEventListener("submit", function (event) {
    var form = event.target;
    var regionId = form.getAttribute("data-listen");
    var region = regionId && document.getElementById(regionId);
    if (!region) {
      return;
    }
    event.preventDefault();
    if (form.hasAttribute("data-busy")) {
      return;
    }
    form.setAttribute("data-busy", "");
    say(region, "Getting it ready.");
    fetch(form.action, {
      method: "POST",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
      body: new URLSearchParams(new FormData(form)),
    })
      .then(function (response) {
        if (!response.ok && (response.headers.get("Content-Type") || "").indexOf("application/json") === -1) {
          // A page, not an answer for this script (such as the access page): show it.
          form.removeAttribute("data-busy");
          form.submit();
          return null;
        }
        return json(response);
      })
      .then(function (status) {
        if (status) {
          follow(form, region, status);
        }
      })
      .catch(function () {
        say(region, NO_ANSWER);
        form.removeAttribute("data-busy");
      });
  });
})();
