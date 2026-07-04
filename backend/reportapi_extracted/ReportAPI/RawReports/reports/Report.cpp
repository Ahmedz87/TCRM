//+------------------------------------------------------------------+
//|                                               Raw Reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "Report.h"
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
CReport::CReport(CReport *next,LPCSTR name,LPCSTR formats):m_file(NULL),m_next(next)
  {
//---
   memset(&m_info,0,sizeof(m_info));
   if(name)    { COPY_STR(m_info.name,name); }
   else        strcpy(m_info.name,"unknown");

   if(formats) { COPY_STR(m_info.formats,formats); }
   else        strcpy(m_info.formats,"HTML format (*.htm)|*.htm|CSV format (*.csv)|*.csv|");

   strcpy(m_info.def_ext,"htm");
   m_info.type=REPORT_TYPE_RAW;
   m_info.id_internal=(m_next ? m_next->Total() : 0);
//---
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
CReport::~CReport()
  {
//---
   if(m_file!=NULL) { fclose(m_file); m_file=NULL; }
   if(m_next!=NULL) { delete m_next;  m_next=NULL; }
//---
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int CReport::GetInfo(const int idx,RepGeneratorInfo *info)
  {
   if(info==NULL) return(FALSE);
//---
   if(idx!=m_info.id_internal) return(m_next ? m_next->GetInfo(idx,info) : FALSE);
   else memcpy(info,&m_info,sizeof(*info));
//---
   return(TRUE);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int CReport::Report(const ReportParams *params)
  {
   if(params==NULL) return(FALSE);
//--- checks
   if(params->id_internal==m_info.id_internal)
     {
      switch(params->extension)
        {
         case 1: return GenerateHTML(params);
         case 2: return GenerateCSV(params);
        }
     }
   else return(m_next ? m_next->Report(params) : FALSE);
//---
   return(FALSE);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
int CReport::Startup(const ReportParams *params)
  {
//--- checks
   if(params==NULL)                                   return(FALSE);
   if(params->trades==NULL || params->trades_total<0) return(FALSE);
   if(params->filepath[0]==0)                         return(FALSE);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)    return(FALSE);
//---
   return(TRUE);
  }
//+------------------------------------------------------------------+
//| Write html header                                                |
//+------------------------------------------------------------------+
void CReport::WriteHeader(LPCSTR title)
  {
   FILE *in;
   char  tmp[256],*cp;
//--- checks
   if(m_file==NULL || title==NULL) return;
//--- head
   fprintf(m_file,"<html><head><title>%s</title>\n",title);
//--- prepare filename
   GetModuleFileName(NULL,tmp,sizeof(tmp)-10);
   if((cp=strrchr(tmp,'\\'))!=NULL) *cp=0;
   strcat(tmp,"styles.tpl");
//--- try to read template
   if((in=fopen(tmp,"rt"))!=NULL)
     {
      while(fgets(tmp,sizeof(tmp)-1,in)!=NULL) fputs(tmp,m_file);
      fclose(in);
     }
   else  // default styles
     {
      fprintf(m_file,"<style type=\"text/css\" media=\"screen\">\n<!--\n"
                     "td     { font: 8pt Tahoma,Arial; }\n"
                     "//-->\n</style>\n");
      fprintf(m_file,"<style type=\"text/css\" media=\"print\">\n<!--\n"
                     "td     { font: 6pt Tahoma,Arial; }\n"
                     "//-->\n</style>\n");
     }
//---
   fprintf(m_file,"</head>\n<body topmargin=1 marginheight=1>\n");
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
