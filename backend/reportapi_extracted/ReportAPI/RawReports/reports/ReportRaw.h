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
class CReportRaw : public CReport
  {
public:
   CReportRaw(CReport *next,LPCSTR name,LPCSTR formats=NULL) :
                     CReport(next,name,formats) { m_info.type|=REPORT_TYPE_REPORTS; }
   int               GenerateHTML(const ReportParams *params);
   int               GenerateCSV(const ReportParams *params);
  };
//+------------------------------------------------------------------+
