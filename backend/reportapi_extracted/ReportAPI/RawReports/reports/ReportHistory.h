//+------------------------------------------------------------------+
//|                                               Raw Reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#pragma once
//---
#include "Report.h"
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
class CReportHistory : public CReport
  {
public:
   CReportHistory(CReport *next,LPCSTR name,LPCSTR formats=NULL) :
                     CReport(next,name,formats) { m_info.type|=REPORT_TYPE_HISTORY; }
   int               GenerateHTML(const ReportParams *params);
   int               GenerateCSV(const ReportParams *params);
  };
//+------------------------------------------------------------------+
