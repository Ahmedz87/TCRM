//+------------------------------------------------------------------+
//|                                        Additional reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#pragma once
//---
#include "Report.h"
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
class CReportCreditFacility : public CReport
  {
public:
   CReportCreditFacility(CReport *next,LPCSTR name,LPCSTR formats=NULL) :
                     CReport(next,name,formats) {};
   int               GenerateHTML(const ReportParams *params);
   int               GenerateCSV(const ReportParams *params);
  };
//+------------------------------------------------------------------+
