//+------------------------------------------------------------------+
//|                                               Raw Reports plugin |
//|                   Copyright 2001-2014, MetaQuotes Software Corp. |
//|                                        http://www.metaquotes.net |
//+------------------------------------------------------------------+
#include "stdafx.h"
#include "ReportOnline.h"
//+------------------------------------------------------------------+
//| Online Users Report                                              |
//+------------------------------------------------------------------+
BOOL CReportOnline::GenerateHTML(const ReportParams* params)
  {
   OnlineUserRecord *user=NULL;
   int               total=0,i,result=TRUE;
   char              tmp[256]="";
//--- checks
   if(params==NULL)                                  return(FALSE);
   if(params->buffer==NULL || params->buffer_size<1) return(FALSE);
   if(params->filepath[0]==0)                        return(FALSE);
   if((total=params->buffer_size/sizeof(*user))<1)   return(FALSE);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)   return(FALSE);
//--- generation
   WriteHeader(m_info.name);
   fprintf(m_file,"<style>\n"
                  ".money { mso-number-format:\\#\\,\\#\\#0\\.00; }\n"
                  "</style>\n");
//--- report header
   fprintf(m_file,"<div align=center>\n");
   fprintf(m_file,"<table cellspacing=1 cellpadding=2 border=0 width=99%%>\n");
   fprintf(m_file,"<tr><td colspan=9><font size=2><b>%s</b></font></td></tr>\n",m_info.name);
   fprintf(m_file,"<tr align=right bgcolor=#c0c0c0>");
   fprintf(m_file,"<td align=left>Login</td><td align=left>Name</td><td>Group</td><td>Country</td>"
                  "<td>Email</td><td>Comment</td><td>Balance</td><td>Credit</td><td>IP</td>");
   fprintf(m_file,"</tr>\n");
//--- report rows
   user=(OnlineUserRecord*)params->buffer;
   for(i=0;i<total;i++,user++)
     {
      //--- background color
      if((i&1)==0) fprintf(m_file,"<tr align=right>");
      else         fprintf(m_file,"<tr align=right bgcolor=#e0e0e0>");
      //--- row
      fprintf(m_file,"<td align=left>%d</td>",user->login);
      fprintf(m_file,"<td nowrap align=left>%s</td>",user->name);
      fprintf(m_file,"<td nowrap>%s</td>",user->group);
      fprintf(m_file,"<td nowrap>%s</td>",user->country);
      fprintf(m_file,"<td nowrap>%s</td>",user->email);
      fprintf(m_file,"<td nowrap>%s</td>",user->comment);
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(user->balance,2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap class=money>%s</td>",ToMoney(user->credit, 2,tmp,sizeof(tmp)-1));
      fprintf(m_file,"<td nowrap>%s</td>",user->ip);
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
BOOL CReportOnline::GenerateCSV(const ReportParams* params)
  {
   OnlineUserRecord *user=NULL;
   int               total=0,i,result=TRUE;
//--- checks
   if(params==NULL)                                  return(FALSE);
   if(params->buffer==NULL || params->buffer_size<1) return(FALSE);
   if(params->filepath[0]==0)                        return(FALSE);
   if((total=params->buffer_size/sizeof(*user))<1)   return(FALSE);
//--- open file
   if(m_file!=NULL) fclose(m_file);
   if((m_file=fopen(params->filepath,"wt"))==NULL)   return(FALSE);
//--- report header
   fprintf(m_file,"%s\n",m_info.name);
   fprintf(m_file,"Login;Name;Group;Email;Country;Comment;Balance;Credit;IP\n");
//--- report rows
   user=(OnlineUserRecord*)params->buffer;
   for(i=0;i<total;i++,user++)
     {
      fprintf(m_file,"%d;%s;%s;%s;%s;%s;%.2lf;%.2lf;%s\n",
              user->login,user->name,user->group,user->email,user->country,
              user->email,user->balance,user->credit,user->ip);
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
