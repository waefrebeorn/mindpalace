# .WET element reference

Lookup table for the framework's public surface. The README in the WET repo
carries the same material with prose; this is the compact form for writing a
control or a binding.

## Elements and their properties

| Element | Kind | Properties | Notes |
|---|---|---|---|
| `label` | control | `text`, `color`, `wrap` | `wrap` wraps at the available width |
| `button` | control | `text`, `color`, `default` | draws a focus ring when focused |
| `textbox` | control | `text`, `password`, `multiline` | `password` masks the drawn text |
| `checkbox` | control | `text`, `checked`, `tri_state` | fires `onchange` with `ev.value` |
| `listbox` | control | `selected`, `count`, `item(i)` | fires `onselect` with `ev.value` = index |
| `progress` | control | `value`, `maximum`, `minimum` | clamped on write |
| `slider` | control | `value`, `minimum`, `maximum`, `step` | fires `onchange` with `ev.value` |
| `separator` | control | `vertical` | 2px rule |
| `groupbox` | panel | `text` | reserves a caption band; children inset |
| `image` | control | `path`, `width`, `height` | pixel buffer is optional |
| `stack` | panel | `spacing`, `orient`, `expand` | `orient` = `vertical`/`horizontal` |
| `dock` | panel | per-child `dock` | 1=left 2=top 3=right 4=bottom 5=fill; unset fills |
| `canvas` | panel | per-child `left`, `top` | absolute positioning |
| `grid` | panel | `columns`, `rows`, per-child `col`, `row` | gaps from the panel default |

## Events

`onclick`, `ondblclick`, `onchange`, `ontextchanged`, `onselect`, `onfocus`,
`onblur`, `onkeydown`, `onkeyup`, `onmousedown`, `onmouseup`, `onmousemove`,
`onpaint`.

A handler is `function(self, ev) ... end`. `ev` carries `kind`, `x`, `y`
(widget-local), `value` and `text`. Events bubble from the control to its
parent panel unless a handler consumes them.

## Script-facing globals

- `wet.applet { title, width, height, content }` -- builds and shows.
- `wet.find(id)` -- a proxy, or nil when the id is unknown.
- `wet.messagebox(text, title)` -- reports through the app's error sink.
- Constructors are also registered bare (`label{...}`) for scripts that
  prefer them; `wet.label{...}` is the canonical form.

## Proxy fields

Reading and writing a proxy reads and writes the live widget, so
`wet.find("name").text = "x"` is a real property assignment.

`text`, `checked`, `value`, `maximum`, `minimum`, `selected`, `count`,
`password`, `id`, `visible`, `enabled`, `spacing`, `columns`, `rows`,
`item(i)`.

## Writing a script that must survive upstream quirks

- Use `children = { ... }` for panel content.
- Put properties AFTER the array items in a table literal, or use a named
  array field.
- `print(4/2)` is `2.0`; `string.gsub` with a table replacement drops
  unmatched characters. See `wubuos-lua-scripting` for the current gap list.
