//+------------------------------------------------------------------+
//|                                                   Reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "HistoryCommon.h"
//+------------------------------------------------------------------+
//| Common History Report                                            |
//+------------------------------------------------------------------+
BOOL CHistoryCommon::GenerateHTML(const ReportParams* params)
  {
   const DailyReport *daily=NULL;
   const UserRecord  *ur   =NULL;
   int                total=0,i,j,count=0,result=TRUE;
   double             total_closed_pl=.0,total_net=.0;
   char               tmp[256]="";
//--- checks
   if(params==NULL)                                   return(FALSE);
   if(params->buffer==NULL || params->buffer_size<1)  return(FALSE);
   if(params->filepath[0]==0)                         return(FALSE);
   if((total=params->buffer_size/sizeof(daily[0]))<1) return(FALSE);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)    return(FALSE);
//--- generation
   WriteHeader(m_info.name);
   fprintf(m_file,"<style>\n"
                  ".money { mso-number-format:\\#\\,\\#\\#0\\.00; }\n"
                  ".date  { mso-number-format:\"yyyy\\.mm\\.dd\"; }\n"
                  "</style>\n");
//--- report header
   fprintf(m_file,"<div align=center>\n");
   fprintf(m_file,"<table cellspacing=1 cellpadding=2 border=0 width=\"99%%\">\n");
   fprintf(m_file,"<tr><td colspan=12><font size=2><b>Common History Report</b> for '%s'",params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s",tmp);
   fprintf(m_file,"</font></td></tr>\n");
//--- report rows
   for(i=0;i<params->group.total;i++)
     {
      if((ur=UserRecordGet(params,params->group_logins[i]))==NULL) continue;
      total_closed_pl=total_net=.0;
      daily=(DailyReport*)params->buffer;
      for(j=0,count=0;j<total;j++,daily++)
        {
         if(daily->login!=ur->login) continue;
         //--- header
         if(count==0)
           {
            fprintf(m_file,"<tr><td colspan=12>A/C No: <b>%d</b>, Name: <b>%s</b>, Group: %s</td></tr>\n",
                            ur->login,ur->name,ur->group);
            fprintf(m_file,"<tr bgcolor=\"#c0c0c0\" align=right>"
                           "<td align=left>Time</td><td align=left>Login</td><td>Balance</td><td>Equity</td>"
                           "<td>Deposit</td><td>Credit</td><td nowrap>Closed P/L</td><td nowrap>Floating P/L</td>"
                           "<td nowrap>Used Margin</td><td nowrap>Free Margin</td>"
                           "<td nowrap>Total Closed P/L</td><td nowrap>Total Net</td>"
                           "</tr>\n");
           }
         //--- background color
         if((count&1)==0) fprintf(m_file,"<tr align=right>");
         else             fprintf(m_file,"<tr align=right bgcolor=\"#e0e0e0\">");
         count++;
         //--- запись
         fprintf(m_file,"<td align=left nowrap class=date>%s</td>",FormatDateTime(daily->ctm,tmp,sizeof(tmp)-1,FALSE));
         fprintf(m_file,"<td align=left>%d</td>",daily->login);
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->balance      ,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->equity       ,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->deposit      ,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->credit       ,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->profit_closed,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->profit       ,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->margin       ,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(daily->margin_free  ,2,tmp,sizeof(tmp)-1));
         total_closed_pl=NormalizeDouble(total_closed_pl+daily->profit_closed,2);
         total_net      =NormalizeDouble(daily->profit+total_closed_pl,2);
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(total_closed_pl,2,tmp,sizeof(tmp)-1));
         fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(total_net      ,2,tmp,sizeof(tmp)-1));
         //---
         fprintf(m_file,"</tr>\n");
         //---
        }
      //--- report progress and check cancellation
      if((i&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->group.total)!=0)
           {
            result=FALSE; break;
           }
      //---
     }
   fprintf(m_file,"</table>\n</div>\n");
   fprintf(m_file,"</body></html>\n");
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
BOOL CHistoryCommon::GenerateCSV(const ReportParams* params)
  {
   const DailyReport *daily=NULL;
   const UserRecord  *ur   =NULL;
   int                total=0,i,j,result=TRUE;
   double             total_closed_pl=.0,total_net=.0;
   char               tmp[256]="";
//--- checks
   if(params==NULL)                                   return(FALSE);
   if(params->buffer==NULL || params->buffer_size<1)  return(FALSE);
   if(params->filepath[0]==0)                         return(FALSE);
   if((total=params->buffer_size/sizeof(daily[0]))<1) return(FALSE);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)    return(FALSE);
//--- report header
   fprintf(m_file,"Common History Report for '%s'",params->group.name);
   FormatDateTime(params->group.from,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," from %s",tmp);
   FormatDateTime(params->group.to-1,tmp,sizeof(tmp)-1,FALSE);
   fprintf(m_file," to %s\n",tmp);
//--- report rows
   for(i=0;i<params->group.total;i++)
     {
      if((ur=UserRecordGet(params,params->group_logins[i]))==NULL) continue;
      fprintf(m_file,"A/C No: %d, Name: %s, Group: %s\n",ur->login,ur->name,ur->group);
      //--- header
      fprintf(m_file,"Time;Login;Balance;Equity;Deposit;Credit;Closed P/L;Floating P/L;"
                  "Used Margin;Free Margin;Total Closed P/L;Total Net\n");
      total_closed_pl=total_net=.0;
      daily=(DailyReport*)params->buffer;
      for(j=0;j<total;j++,daily++)
        {
         if(ur->login!=daily->login) continue;
         //--- row
         FormatDateTime(daily->ctm,tmp,sizeof(tmp)-1,FALSE);
         fprintf(m_file,"%s;%d;",tmp,daily->login);
         fprintf(m_file,"%.2lf;%.2lf;",daily->balance,daily->equity);
         fprintf(m_file,"%.2lf;%.2lf;",daily->deposit,daily->credit);
         fprintf(m_file,"%.2lf;%.2lf;",daily->profit_closed,daily->profit);
         fprintf(m_file,"%.2lf;%.2lf;",daily->margin,daily->margin_free);
         total_closed_pl=NormalizeDouble(total_closed_pl+daily->profit_closed,2);
         total_net      =NormalizeDouble(daily->profit+total_closed_pl,2);
         fprintf(m_file,"%.2lf;%.2lf\n",total_closed_pl,total_net);
         //---
        }
      //--- report progress and check cancellation
      if((i&7)==0 && params->fn_progress!=NULL)
         if(params->fn_progress(params->custom,i,params->group.total)!=0)
           {
            result=FALSE; break;
           }
      //---
     }
   fclose(m_file);
   m_file=NULL;
//---
   return(result);
  }
//+------------------------------------------------------------------+
//|                                                                  |
//+------------------------------------------------------------------+
