//+------------------------------------------------------------------+
//|                                               Raw Reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "ReportJournal.h"
//+------------------------------------------------------------------+
//| Journal Report                                                   |
//+------------------------------------------------------------------+
BOOL CReportJournal::GenerateHTML(const ReportParams* params)
  {
   ServerLog *logs=NULL;
   int        total=0,i,result=TRUE;
//--- checks
   if(params==NULL)                                  return(FALSE);
   if(params->buffer==NULL || params->buffer_size<1) return(FALSE);
   if(params->filepath[0]==0)                        return(FALSE);
   if((total=params->buffer_size/sizeof(*logs))<1)   return(FALSE);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)   return(FALSE);
//--- generation
   WriteHeader(m_info.name);
   fprintf(m_file,"<div align=center>\n");
   fprintf(m_file,"<table cellspacing=1 cellpadding=2 border=0 width=99%%>\n");
//--- report header
   fprintf(m_file,"<tr><td colspan=3><font size=2><b>%s</b>",m_info.name);
//--- find "from" in logs
   logs=(ServerLog*)params->buffer;
   for(i=0;i<total;i++,logs++)
      if(logs->code==CmdDay)
        {
         fprintf(m_file," from %s",logs->time);
         break;
        }
//--- find "to" in logs
   logs=((ServerLog*)params->buffer)+total-1;
   for(i=total-1;i>=0;i--,logs--)
      if(logs->code==CmdDay)
        {
         fprintf(m_file," to %s",logs->time);
         break;
        }
   fprintf(m_file,"</font></td></tr>\n");
//--- table header
   fprintf(m_file,"<tr bgcolor=#c0c0c0>");
   fprintf(m_file,"<td width=20%%>Time</td><td width=15%%>IP</td><td width=65%%>Message</td>");
   fprintf(m_file,"</tr>\n");
//--- report rows
   logs=(ServerLog*)params->buffer;
   for(i=0;i<total;i++,logs++)
     {
      //--- background color
      if(logs->code==CmdErr || logs->code==CmdAtt)
        {
         if((i&1)==0) fprintf(m_file,"<tr align=left bgcolor=#ffe8e8>");
         else         fprintf(m_file,"<tr align=left bgcolor=#ffd0d0>");
        }
      else
        {
         if((i&1)==0) fprintf(m_file,"<tr align=left>");
         else         fprintf(m_file,"<tr align=left bgcolor=#e0e0e0>");
        }
      //--- row
      fprintf(m_file,"<td nowrap>%s</td>",logs->time);
      fprintf(m_file,"<td nowrap>%s</td>",logs->ip);
      fprintf(m_file,"<td nowrap>%s</td>",logs->message);
      fprintf(m_file,"</tr>\n");
      //--- report progress and check cancellation
      if((i&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,total)!=0)
           {
            result=FALSE; break;
           }
      //---
     }
   fprintf(m_file,"</table>\n</div>\n");
   fprintf(m_file,"</body></html>\n");
   fclose(m_file);
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
BOOL CReportJournal::GenerateCSV(const ReportParams* params)
  {
   ServerLog *logs=NULL;
   int        total=0,i,result=TRUE;
//--- checks```
   if(params==NULL)                                  return(FALSE);
   if(params->buffer==NULL || params->buffer_size<1) return(FALSE);
   if(params->filepath[0]==0)                        return(FALSE);
   if((total=params->buffer_size/sizeof(*logs))<1)   return(FALSE);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)   return(FALSE);
//--- report header
   fprintf(m_file,"%s",m_info.name);
   logs=(ServerLog*)params->buffer;
   for(i=0;i<total;i++,logs++)
      if(logs->code==CmdDay) { fprintf(m_file," from %s",logs->time); break; }
   logs=((ServerLog*)params->buffer)+total-1;
   for(i=total-1;i>=0;i--,logs--)
      if(logs->code==CmdDay) { fprintf(m_file," to %s",logs->time); break; }
   fprintf(m_file,"\n");
   fprintf(m_file,"Time;IP;Message\n");
//--- report rows
   logs=(ServerLog*)params->buffer;
   for(i=0;i<total;i++,logs++)
     {
      fprintf(m_file,"%s;%s;%s\n",logs->time,logs->ip,logs->message);
      //--- report progress and check cancellation
      if((i&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,total)!=0)
           {
            result=FALSE; break;
           }
     }
   fclose(m_file);
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
