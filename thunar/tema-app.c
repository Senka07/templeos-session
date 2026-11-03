/* Modulo GTK3 que troca o tema so do processo que o carrega.
 *
 * Com GTK_THEME=TempleOS-Thunar o Thunar ficaria com o tema, mas todo programa
 * que ele abre (editor, visualizador, navegador) herdaria a variavel e sairia
 * com o tema tambem. Aqui o tema entra como configuracao do proprio processo
 * (GtkSettings, que vale so dentro dele) e as variaveis que trouxeram o
 * modulo saem do ambiente antes de o Thunar abrir qualquer coisa.
 *
 * TEMPLEOS_ICONES_GTK faz o mesmo com o tema de icones.
 *
 * Uso: GTK_MODULES=/caminho/tema-app.so TEMPLEOS_TEMA_GTK=TempleOS-Thunar \
 *      TEMPLEOS_ICONES_GTK=TempleOS-Thunar thunar
 * Compilar: gcc -shared -fPIC -o tema-app.so tema-app.c $(pkg-config --cflags --libs gtk+-3.0)
 */
#include <gtk/gtk.h>
#include <string.h>

/* Tira do GTK_MODULES so este modulo; os outros (canberra etc.) ficam. */
static void
tira_do_gtk_modules (void)
{
  const gchar *atual = g_getenv ("GTK_MODULES");
  if (atual == NULL)
    return;
  gchar **partes = g_strsplit (atual, ":", -1);
  GPtrArray *resto = g_ptr_array_new ();
  for (gchar **p = partes; *p != NULL; p++)
    if (**p != '\0' && strstr (*p, "tema-app") == NULL)
      g_ptr_array_add (resto, *p);
  g_ptr_array_add (resto, NULL);
  if (resto->len > 1)
    {
      gchar *novo = g_strjoinv (":", (gchar **) resto->pdata);
      g_setenv ("GTK_MODULES", novo, TRUE);
      g_free (novo);
    }
  else
    g_unsetenv ("GTK_MODULES");
  g_ptr_array_free (resto, TRUE);
  g_strfreev (partes);
}

G_MODULE_EXPORT void
gtk_module_init (gint *argc, gchar ***argv)
{
  const gchar *tema = g_getenv ("TEMPLEOS_TEMA_GTK");
  const gchar *icones = g_getenv ("TEMPLEOS_ICONES_GTK");
  GtkSettings *cfg = gtk_settings_get_default ();
  if (tema != NULL && *tema != '\0')
    g_object_set (cfg, "gtk-theme-name", tema, NULL);
  if (icones != NULL && *icones != '\0')
    g_object_set (cfg, "gtk-icon-theme-name", icones, NULL);
  g_unsetenv ("TEMPLEOS_TEMA_GTK");
  g_unsetenv ("TEMPLEOS_ICONES_GTK");
  tira_do_gtk_modules ();
}
