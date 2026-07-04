//+------------------------------------------------------------------+
//|                                                   Reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "reports\HistoryCommon.h"
#include "reports\HistoryEquity.h"
#include "reports\HistoryProfitLoss.h"
//+------------------------------------------------------------------+
//| DLL exports                                                      |
//+------------------------------------------------------------------+
extern "C"
  {
   REPORTS_API int   RepGetVersion(void);
   REPORTS_API int   RepGetModuleInfo(char *buffer,int ccmax);
   REPORTS_API BOOL  RepGetGeneratorInfo(int index,RepGeneratorInfo *info);
   REPORTS_API BOOL  RepGenerateReport(ReportParams *params);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
CReport *ExtReports=NULL;
//+------------------------------------------------------------------+
//| Entry point                                                      |
//+------------------------------------------------------------------+
BOOL APIENTRY DllMain(HANDLE hModule, DWORD dwReason, void*)
  {
//---
   switch(dwReason)
     {
      case DLL_PROCESS_ATTACH:
         if(ExtReports==NULL)
           {
            ExtReports=new CHistoryCommon(NULL,"Common History Report");
            ExtReports=new CHistoryEquity(ExtReports,"Equity Report");
            ExtReports=new CHistoryProfitLoss(ExtReports,"Profit and Loss Report");
           }
         break;
      case DLL_PROCESS_DETACH:
         if(ExtReports!=NULL) { delete ExtReports; ExtReports=NULL; }
         break;
     }
//---
   return(TRUE);
  }
//+------------------------------------------------------------------+
//| Plugin version                                                   |
//+------------------------------------------------------------------+
REPORTS_API int RepGetVersion(void) { return(REPORTS_VERSION); }
//+------------------------------------------------------------------+
//| Plugin name                                                      |
//+------------------------------------------------------------------+
REPORTS_API int RepGetModuleInfo(char *buffer,int ccmax)
  {
//---
   if(buffer!=NULL && ccmax>1)
     {
      strncpy(buffer,"Additional Reports",ccmax);
      buffer[ccmax-1]=0;
     }
//---
   return(ExtReports!=NULL ? ExtReports->Total() : 0);
  }
//+------------------------------------------------------------------+
//| Report definition                                                |
//+------------------------------------------------------------------+
REPORTS_API BOOL RepGetGeneratorInfo(int index,RepGeneratorInfo *info)
  {
   return(ExtReports!=NULL ? ExtReports->GetInfo(index,info) : FALSE);
  }
//+------------------------------------------------------------------+
//| Report generation                                                |
//+------------------------------------------------------------------+
REPORTS_API BOOL RepGenerateReport(ReportParams *params)
  {
   return(ExtReports!=NULL ? ExtReports->Report(params) : FALSE);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
