//+------------------------------------------------------------------+
//|                                                   Reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#pragma once
//---
#include "sync.h"
//---
extern char ExtProgramPath[MAX_PATH];
//+------------------------------------------------------------------+
//| Logger                                                           |
//+------------------------------------------------------------------+
class CLogger
  {
private:
   CSync             m_sync;
   char             *m_buffer;
   FILE             *m_file;

public:
                     CLogger(void);
                    ~CLogger();
   void              Out(LPCSTR msg,...);
   void              Flush(void);
  };
//---
extern CLogger ExtLogger;
//+------------------------------------------------------------------+
