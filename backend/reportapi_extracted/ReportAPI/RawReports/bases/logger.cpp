//+------------------------------------------------------------------+
//|                                                   Reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "Logger.h"
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
char  ExtProgramPath[MAX_PATH]={0};
//---
CLogger ExtLogger;
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
CLogger::CLogger(void)
  {
   m_buffer=(char*)malloc(8192);
   m_file=NULL;
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
CLogger::~CLogger(void)
  {
//---
   m_sync.Lock();
   if(m_file!=NULL)   { fclose(m_file); m_file=NULL;   }
   if(m_buffer!=NULL) { free(m_buffer); m_buffer=NULL; }
   m_sync.Unlock();
//---
  }
//+------------------------------------------------------------------+
//| Log out to the file                                              |
//+------------------------------------------------------------------+
void CLogger::Out(LPCSTR msg,...)
  {
   SYSTEMTIME st;
//--- checks and time
   if(msg==NULL || m_buffer==NULL) return;
   GetLocalTime(&st);
   m_sync.Lock();
//--- open file if necessary
   if(m_file==NULL)
     {
      sprintf(m_buffer,"%s\\RawReports.log",ExtProgramPath);
      if((m_file=fopen(m_buffer,"at"))==NULL) { m_sync.Unlock(); return; }
     }
//--- access variable-argument list
   va_list arg_ptr;
   va_start(arg_ptr, msg);
   vsprintf(m_buffer,msg,arg_ptr);
   va_end(arg_ptr);
//--- write to file
   fprintf(m_file,"%04d.%02d.%02d %02d:%02d:%02d %s\n",st.wYear,st.wDay,st.wMonth,st.wHour,st.wMinute,st.wSecond,m_buffer);
//---
   m_sync.Unlock();
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
void CLogger::Flush(void)
  {
   m_sync.Lock();
//---
   if(m_file!=NULL) { fclose(m_file); m_file=NULL; }
//---
   m_sync.Unlock();
  }
//+------------------------------------------------------------------+
