/*
 * glx_fullscreen.c — minimal fullscreen fixed-function GLX skeleton.
 * Build WITHOUT dev packages (versioned libs only):
 *   gcc -O2 -o app glx_fullscreen.c -l:libGL.so.1 -l:libX11.so.6 -lm
 * Draw rotating scene, exit on any key. Core GL only (NO glu.h required).
 */
#include <X11/Xlib.h>
#include <GL/gl.h>
#include <GL/glx.h>
#include <math.h>
#include <stdio.h>
#include <unistd.h>
#include <time.h>

static int W=1280, H=800;
static double g_t=0.0;

/* Example object. REMEMBER: while GL_LIGHTING is enabled, glColor is ignored;
 * set material color instead or the object renders gray/invisible:
 *   GLfloat m[4]={1,0.85f,0.2f,1}; glMaterialfv(GL_FRONT_AND_BACK,
 *                          GL_AMBIENT_AND_DIFFUSE, m); */
static void draw(void){
  glEnable(GL_LIGHTING); glEnable(GL_LIGHT0);
  float dif[4]={1,1,1,1}, pos[4]={-3,6,5,1};
  glLightfv(GL_LIGHT0,GL_DIFFUSE,dif); glLightfv(GL_LIGHT0,GL_POSITION,pos);
  glPushMatrix();
  glRotated(fmod(g_t*35.0,360.0),0,1,0);      /* continuous rotation */
  glBegin(GL_QUADS);
  glNormal3f(0,0,1); glVertex3f(-1,-1,0); glVertex3f(1,-1,0);
                     glVertex3f(1,1,0);  glVertex3f(-1,1,0);
  glEnd();
  glPopMatrix();
  glDisable(GL_LIGHTING);
}

static void render(void){
  glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
  glViewport(0,0,W,H);
  glMatrixMode(GL_PROJECTION); glLoadIdentity();
  double fov=60.0*M_PI/180.0, zn=0.1, zf=60.0, asp=(double)W/H;
  double top=zn*tan(fov/2), right=top*asp;
  glFrustum(-right,right,-top,top,zn,zf);     /* core GL, no gluPerspective */
  glMatrixMode(GL_MODELVIEW); glLoadIdentity();
  glTranslatef(0,0,-6);
  draw();
}

int main(int argc,char**argv){
  Display*d=XOpenDisplay(NULL); if(!d)return 1;
  int s=DefaultScreen(d); W=DisplayWidth(d,s); H=DisplayHeight(d,s);
  static int att[]={GLX_DOUBLEBUFFER,True,GLX_RGBA,True,GLX_DEPTH_SIZE,24,None};
  XVisualInfo*vi=glXChooseVisual(d,s,att); if(!vi)return 1;
  GLXContext cx=glXCreateContext(d,vi,NULL,True); if(!cx)return 1;
  XSetWindowAttributes swa={0};
  swa.colormap=XCreateColormap(d,RootWindow(d,s),vi->visual,AllocNone);
  swa.override_redirect=True;
  Window win=XCreateWindow(d,RootWindow(d,s),0,0,W,H,0,vi->depth,InputOutput,
                           vi->visual,CWColormap|CWOverrideRedirect,&swa);
  XMapRaised(d,win);
  XGrabKeyboard(d,RootWindow(d,s),True,GrabModeAsync,GrabModeAsync,CurrentTime);
  glXMakeCurrent(d,win,cx);
  glEnable(GL_DEPTH_TEST); glClearColor(0.02f,0.02f,0.05f,1); glShadeModel(GL_SMOOTH);
  struct timespec t0,t; clock_gettime(CLOCK_MONOTONIC,&t0);
  int run=1;
  while(run){
    while(XPending(d)){ XEvent e; XNextEvent(d,&e);
      if(e.type==KeyPress||e.type==DestroyNotify) run=0; }
    if(!run)break;
    clock_gettime(CLOCK_MONOTONIC,&t);
    g_t=(t.tv_sec-t0.tv_sec)+(t.tv_nsec-t0.tv_nsec)/1e9;
    render(); glXSwapBuffers(d,win); usleep(15000);
  }
  glXDestroyContext(d,cx); XCloseDisplay(d); return 0;
}
