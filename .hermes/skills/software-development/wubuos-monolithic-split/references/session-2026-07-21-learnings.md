# Session 2026-07-21 Learnings

## Calc Test Linker Fix Pattern

When a test links GUI/window manager code, compile all WM `.c` files directly rather than using prebuilt `.o` files (which may be missing). Pattern:

```makefile
test_calc:
	$(CC) -O0 -g -std=c11 -DVBE_HOSTED -D_POSIX_C_SOURCE=200809L \
		-I$(GUI) -I$(KERNEL) -I$(COMP) -I$(JIT) -I$(APPS) -I$(APPS)/calc -I$(HOSTED) -I$(RT) \
		$(GUI)/wm.c $(GUI)/wm_window.c $(GUI)/wm_input.c \
		$(GUI)/wm_clock.c $(GUI)/wm_ctxmenu_engine.c \
		$(GUI)/wm_window_state.c $(GUI)/wm_layout.c \
		$(GUI)/wm_render.c $(GUI)/wm_taskbar.c \
		$(GUI)/wm_desktop.c $(GUI)/wm_icons.c \
		$(GUI)/wm_icon_glyphs.c $(GUI)/wm_systray.c \
		$(GUI)/wm_ctxmenu.c $(GUI)/wm_holyc_term.c \
		$(GUI)/wubu_wallpaper.c $(GUI)/wubu_theme.c $(GUI)/wm_test_stub.c \
		$(KERNEL)/vbe.c $(GUI)/wubu_notify.c $(GUI)/wubu_settings.c \
		$(GUI)/wubu_settings_defaults.o $(GUI)/wubu_settings_io.o \
		$(GUI)/wubu_json.c $(GUI)/wubu_trash.c \
		$(COMP)/holyc_codegen.c $(COMP)/holyc_parse.c $(COMP)/holyc_parse_ast.c \
		$(COMP)/holyc_lexer.c $(COMP)/holyc_codegen_emit.c \
		$(COMP)/holyc_codegen_expr.c $(COMP)/holyc_codegen_stmt.c \
		$(COMP)/holyc_codegen_api.c $(JIT_SRCS) $(RT)/wubu_spawn.c \
		$(RT)/wubu_session.c $(RT)/wubu_compat_db.c $(RT)/wubu_container.c \
		$(RT)/wubu_arch.c $(GUI)/window_chrome.c \
		$(APPS)/calc/calc.c $(APPS)/calc/calc_math.c \
		$(APPS)/calc/calc_test.c -o $(APPS)/calc/calc_test -lm
```

## Missing Test Target Pattern

When a test is referenced in tier aggregators but the target doesn't exist, add it with proper linking:

```makefile
test_trash:
	$(CC) -O0 -g -std=c11 -D_POSIX_C_SOURCE=200809L -DWUBU_NO_LIBM \
		-I$(GUI) -I$(KERNEL) \
		$(GUI)/wubu_trash.c $(GUI)/wubu_settings.c $(GUI)/wubu_settings_defaults.o \
		$(GUI)/wubu_settings_io.o $(GUI)/wubu_json.c $(GUI)/wubu_theme.c \
		$(RT)/wubu_arch.c \
		$(GUI)/wubu_trash_test.c \
		-o $(GUI)/wubu_trash_test
	$(GUI)/wubu_trash_test
```