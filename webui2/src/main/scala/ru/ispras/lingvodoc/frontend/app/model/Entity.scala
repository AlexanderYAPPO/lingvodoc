package ru.ispras.lingvodoc.frontend.app.model

import upickle.Js
import upickle.default._

import scala.scalajs.js
import scala.scalajs.js.annotation.JSExportAll
import scala.scalajs.js.JSConverters._
import org.scalajs.dom.console
import upickle.Js.Obj



@JSExportAll
case class Entity(override val clientId: Int,
                  override val objectId: Int,
                  var parentClientId: Int,
                  var parentObjectId: Int,
                  var level: String,
                  var published: Boolean,
                  var markedForDeletion: Boolean,
                  var entityType: String,
                  var content: String,
                  var localeId: Int
                 ) extends Object(clientId, objectId) {

  var entities: js.Array[Entity] = js.Array()
  var metadata: js.Array[MetaData] = js.Array()
}

object Entity {
  implicit val writer = upickle.default.Writer[Entity] {
    case t => Js.Obj(
      ("client_id", Js.Num(t.clientId)),
      ("object_id", Js.Num(t.objectId)),
      ("parent_client_id", Js.Num(t.parentClientId)),
      ("parent_object_id", Js.Num(t.parentObjectId)),
      ("level", Js.Str(t.level)),
      ("published", if (t.published) Js.True else Js.False),
      ("marked_for_deletion", if (t.markedForDeletion) Js.True else Js.False),
      ("entity_type", Js.Str(t.entityType)),
      ("content", Js.Str(t.content)),
      ("locale_id", Js.Num(t.localeId))
    )
  }


  implicit val reader = upickle.default.Reader[Entity] {
    case jsobj: Js.Obj =>
      (new ((Js.Obj) => Entity) {
        def apply(jsVal: Js.Obj): Entity = {
          val clientId = jsVal("client_id").asInstanceOf[Js.Num].value.toInt
          val objectId = jsVal("object_id").asInstanceOf[Js.Num].value.toInt
          val parentClientId = jsVal("parent_client_id").asInstanceOf[Js.Num].value.toInt
          val parentObjectId = jsVal("parent_object_id").asInstanceOf[Js.Num].value.toInt
          val level = jsVal("level").asInstanceOf[Js.Str].value
          val entityType = jsVal("entity_type").asInstanceOf[Js.Str].value
          val content = jsVal("content").asInstanceOf[Js.Str].value

          val localeId = jsVal("locale_id") match {
            case e: Js.Num => jsVal("locale_id").asInstanceOf[Js.Num].value.toInt
            case _ => -1
          }

          val isPublished = jsVal("published") match {
            case Js.True => true
            case Js.False => false
            case _ => false
          }

          val isMarkedForDeletion = jsVal("marked_for_deletion") match {
            case Js.True => true
            case Js.False => false
            case _ => false
          }

          val e = Entity(clientId, objectId, parentClientId, parentObjectId, level, isPublished, isMarkedForDeletion, entityType, content, localeId)

          // get array of entities
          val entities = jsVal.value.find(_._1 == "contains").getOrElse(("contains", Js.Arr()))._2.asInstanceOf[Js.Arr]

          // parse list of subentities
          var subEntities = Seq[Entity]()
          for (jsEntity <- entities.value) {
            // skip non-object elements
            jsEntity match {
              case js1: Obj => subEntities = subEntities :+ apply(js1)
              case _ =>
            }
          }
          e.entities = subEntities.toJSArray
          e
        }
      })(jsobj)
  }

}