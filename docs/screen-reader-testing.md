# Testing Dogear's web page with a screen reader

Dogear's web page (`dogear serve`) is built for people who use screen readers, and
automated checks run on every change (axe-core, in `scripts/check-web-a11y.sh`). Automated
checks find only some problems. This is the plan for the rest: real people, with the
screen readers they use every day, doing the tasks below.

**Status:** no one has run this plan yet. Each combination below lists who tested it, and
when, once someone has.

## Who can help

Anyone who uses a screen reader, at any level. You don't need to know anything about
programming. Testing one combination, or even one task, helps. A helper can set Dogear up
for you (the README's "Use it in a web browser" section), or you can do it yourself.

## The combinations

Each line is a screen reader, the browser to use with it, and the system. The first four
are the most used, so they come first.

1. NVDA with Firefox, on Windows.
2. NVDA with Chrome, on Windows.
3. JAWS with Chrome, on Windows.
4. VoiceOver with Safari, on an iPhone (using `dogear serve --lan` on a computer on the same
   Wi-Fi network).
5. VoiceOver with Safari, on a Mac.
6. TalkBack with Chrome, on an Android phone (using `dogear serve --lan`).
7. JAWS with Edge, on Windows.
8. Narrator with Edge, on Windows.
9. Orca with Firefox, on Linux.

Also, with no screen reader:

10. Keyboard only (no mouse), in any browser.
11. Windows contrast themes (Settings, Accessibility, Contrast themes), with Edge.
12. Browser zoom at 200% and 400%, and a phone held upright, with large text turned on.
13. A screen magnifier (ZoomText, Windows Magnifier, or macOS Zoom).

## What you need

- A computer with Dogear installed, and the web page running.
- A short book file. The test book in Dogear's repository works:
  `tests/fixtures/robert-louis-stevenson_the-strange-case-of-dr-jekyll-and-mr-hyde.epub`.
  It is in the public domain.
- About 30 minutes. Making the book takes a few minutes of that.

## The tasks

For each task, note whether you could do it, anything your screen reader said that was
confusing or missing, and anything that took longer than it should.

1. **Get in.** Open the access link Dogear showed when it started. You should land on the
   page titled "Your books", whose main heading is "Make a talking book". Then open the
   page again in a private window, without the key: you should hear that the page needs
   the access link, and be able to type the key into a form to get in.
2. **Find your way around.** On "Your books", list the headings, the landmarks, and the
   links. Is it clear what the page is for and where the Help page is? Use the skip link.
3. **Upload a book.** Find the book file control, choose the test book, and upload it.
   While Dogear reads the book, you should hear a short status. When it is done, you
   should be on "Choose what to make".
4. **Make a mistake on purpose.** On "Choose what to make", uncheck every section and
   submit. You should land on a list of problems at the top of the page, each a link to
   the field it is about. Follow a link: you should be taken to that field. The page title
   should start with "Error".
5. **Choose and start.** Check one or two things to make (try "M4B audiobook"), keep the
   voice, pick a speed, check only sections 1 and 2, and choose Start making. Does each
   group of choices announce its question (its legend) and each choice its explanation?
6. **Follow progress.** On the book's page, listen for progress. New progress should be
   announced politely, once, without interrupting you, and without repeating. If
   JavaScript is off, the "Check progress" link should give you the latest. Stop the book
   with "Stop making this book", then choose "Start again": it should carry on.
7. **Download.** When the book is ready, find the download links. Each should say what it
   is and its size. Download one and check it plays.
8. **Fix a word.** On the book's page, follow "check how words are said" and choose
   Check the words. You should hear when the list is ready. Move through the words by
   heading: each group should start with the word, then how often it comes up. Choose
   Listen on one: you should hear "Getting it ready", then the word, with nothing spoken
   over it, and nothing should play until you choose Listen. The player should be named
   "Recording of" the word. Type a spelling in its "Say it like" field (such as
   "utter son" for Utterson), choose Save, and Listen again. Then open Pronunciations from
   the links at the top of the page and find the word there.
9. **Delete.** Delete the book. You should be asked to confirm first, then be back on
   "Your books" with a message saying it was deleted.
10. **Help.** Open Help. Is it clear how to make a book, how to fix a word, and how to use
    Dogear from a phone?

For the combinations without a screen reader (10 to 13), do the same tasks and also check:
everything can be reached and used with the keyboard; you can always see where the
keyboard focus is; nothing needs scrolling sideways; nothing is lost or overlaps when text
is large; and everything is still visible in a contrast theme.

## Reporting

Open an issue at <https://github.com/18hrshift/dogear-app/issues/new/choose> with the
"Accessibility barrier" form, one issue per problem. If everything worked, that's worth
reporting too: open one issue titled "Screen reader test: " followed by the combination,
such as "Screen reader test: NVDA 2026.3 with Firefox 145 on Windows 11", and say which
tasks you did. If you'd rather not use GitHub, ask the person who set Dogear up for you to
pass it on.

Each problem is a bug, and is fixed before the page is called tested with that
combination.
