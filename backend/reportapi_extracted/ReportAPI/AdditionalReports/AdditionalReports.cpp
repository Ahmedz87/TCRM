//+------------------------------------------------------------------+
//|                                        Additional reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "reports\ReportClosedTrades.h"
#include "reports\ReportSummary.h"
#include "reports\ReportSegregated.h"
#include "reports\ReportDepositWithdrawal.h"
#include "reports\ReportCreditFacility.h"
#include "reports\ReportCommissions.h"
#include "reports\ReportDetailedCommissions.h"
#include "reports\ReportWithholdingTax.h"
#include "reports\ReportAgents.h"
#include "reports\ReportPhone.h"
#include "reports\ReportMarginCall.h"
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
            ExtReports=new CReportClosedTrades(NULL,"Closed Trades Report");
            ExtReports=new CReportSummary(ExtReports,"Summary Report");
            ExtReports=new CReportSegregated(ExtReports,"Segregated Report");
            ExtReports=new CReportDepositWithdrawal(ExtReports,"Deposit and Withdrawal Report");
            ExtReports=new CReportCreditFacility(ExtReports,"Credit Facility Report");
            ExtReports=new CReportCommissions(ExtReports,"Commissions Report");
            ExtReports=new CReportDetailedCommissions(ExtReports,"Detailed Commissions Report");
            ExtReports=new CReportWithholdingTax(ExtReports,"Withholding Tax Statement");
            ExtReports=new CReportAgents(ExtReports,"Agents Report");
            ExtReports=new CReportPhone(ExtReports,"Phone Report");
            ExtReports=new CReportMarginCall(ExtReports,"Margin Call Report");
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
