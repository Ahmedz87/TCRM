//+------------------------------------------------------------------+
//|                                        Commission reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
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
CReport * ExtReports=NULL;
char      ExtProgramPath[256];
char      ExtProgramFile[256];
//+------------------------------------------------------------------+
//| Entry point                                                      |
//+------------------------------------------------------------------+
BOOL APIENTRY DllMain(HANDLE hModule, DWORD dwReason, void*)
  {
   char *cp;
//---
   switch(dwReason)
     {
      case DLL_PROCESS_ATTACH:
         //--- добавим отчеты если их еще нет
         if(ExtReports==NULL)
            ExtReports=new CCommissionReport(NULL,"Commission Report");
         //--- вытащим заодно пути
         //GetModuleFileName((HINSTANCE)hModule,ExtProgramFile,sizeof(ExtProgramFile)-1);
         GetModuleFileName((HINSTANCE)NULL,ExtProgramFile,sizeof(ExtProgramFile)-1);
         COPY_STR(ExtProgramPath,ExtProgramFile);
         if((cp=strrchr(ExtProgramPath,'\\'))!=NULL) *cp=0;
         //---
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
      strncpy(buffer,"Commission Reports",ccmax);
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

